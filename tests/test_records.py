import sqlite3
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import patch

import qrcode
import streamlit as st
from PIL import Image
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

import database as db
from backup_utils import create_backup, read_backup
from qr_utils import generate_qr_code

ROOT = Path(__file__).resolve().parents[1]


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.db'
        db.initialize_db(self.path)

    def test_ids_are_permanent_and_never_reused(self):
        self.assertEqual(db.create_record(self.path), 'REC-0001')
        self.assertEqual(db.create_record(self.path), 'REC-0002')
        with sqlite3.connect(self.path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE records SET record_id = 'changed' WHERE record_id = 'REC-0001'")
        db.delete_records(self.path, ['REC-0001', 'REC-0002'])
        self.assertEqual(db.create_record(self.path), 'REC-0003')
        self.assertEqual(db.get_record(self.path, 'REC-0003')['values'], {})
        self.assertIsNone(db.get_record(self.path, 'REC-0003')['qr_filename'])

    def test_field_identity_limits_and_deletion(self):
        first = db.get_fields(self.path)[0]['id']
        db.save_field_name(self.path, first, 'Machine ID')
        db.add_field(self.path)
        second = db.get_fields(self.path)[1]['id']
        db.save_field_name(self.path, second, 'beli')
        record_id = db.create_record(self.path)
        db.save_record_value(self.path, record_id, first, 'M-123')
        db.save_record_value(self.path, record_id, second, '2026')
        db.save_field_name(self.path, first, 'Machine')
        self.assertEqual(db.get_record(self.path, record_id)['values'][first], 'M-123')
        for name in ['', 'elevenchars', 'MACHINE', 'QR Code', 'Record ID']:
            with self.assertRaises(ValueError):
                db.save_field_name(self.path, second, name)
        db.remove_field(self.path, second)
        self.assertEqual(db.get_record(self.path, record_id)['values'], {first: 'M-123'})
        for _ in range(5):
            db.add_field(self.path)
        with self.assertRaises(ValueError):
            db.add_field(self.path)
        db.delete_records(self.path, [record_id])
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM record_values').fetchone()[0], 0)

    def test_migration_preserves_existing_records_once(self):
        legacy = Path(self.temp.name) / 'legacy.db'
        with sqlite3.connect(legacy) as connection:
            connection.executescript("""
                CREATE TABLE field_settings (sort_order INTEGER, field_name TEXT);
                INSERT INTO field_settings VALUES (0, 'Machine ID'), (1, 'beli');
                CREATE TABLE equipment (id INTEGER, record_id TEXT, qr_filename TEXT);
                INSERT INTO equipment VALUES (7, 'REC-0001', 'REC-0001.png'), (11, 'REC-0005', NULL);
                CREATE TABLE equipment_custom_fields (equipment_id INTEGER, field_name TEXT, field_value TEXT);
                INSERT INTO equipment_custom_fields VALUES (7, 'Machine ID', 'M-100'), (11, 'beli', '2026');
            """)
        db.initialize_db(legacy)
        db.initialize_db(legacy)
        records = db.get_records(legacy)
        self.assertEqual([row['record_id'] for row in records], ['REC-0001', 'REC-0005'])
        self.assertEqual(records[0]['qr_filename'], 'REC-0001.png')
        self.assertEqual(list(records[0]['values'].values()), ['M-100'])
        self.assertEqual(list(records[1]['values'].values()), ['2026'])
        self.assertEqual(db.create_record(legacy), 'REC-0006')
        db.delete_records(legacy, ['REC-0001'])
        db.initialize_db(legacy)
        self.assertIsNone(db.get_record(legacy, 'REC-0001'))

    def test_qr_payload_is_only_record_id(self):
        qr = qrcode.QRCode()
        with patch('qr_utils.qrcode.QRCode', return_value=qr), patch.object(qr, 'add_data', wraps=qr.add_data) as add_data:
            filename = generate_qr_code('REC-0003', Path(self.temp.name))
        add_data.assert_called_once_with('REC-0003')
        with Image.open(Path(self.temp.name) / filename) as image:
            image.verify()
        with self.assertRaises(ValueError):
            generate_qr_code('../escape', Path(self.temp.name))

    def test_qr_resets_only_when_last_saved_value_disappears(self):
        first = db.get_fields(self.path)[0]['id']
        db.save_field_name(self.path, first, 'Name')
        db.add_field(self.path)
        second = db.get_fields(self.path)[1]['id']
        db.save_field_name(self.path, second, 'Location')
        emptied = db.create_record(self.path)
        retained = db.create_record(self.path)
        for record_id in [emptied, retained]:
            db.save_record_value(self.path, record_id, first, 'Machine')
            db.save_record_qr(self.path, record_id, f'{record_id}.png')
        db.save_record_value(self.path, retained, second, 'Lab')
        db.remove_field(self.path, first)
        self.assertIsNone(db.get_record(self.path, emptied)['qr_filename'])
        self.assertEqual(db.get_record(self.path, retained)['qr_filename'], f'{retained}.png')
        db.save_record_value(self.path, retained, second, ' \t\n\u00a0')
        self.assertIsNone(db.get_record(self.path, retained)['qr_filename'])
        with self.assertRaises(ValueError):
            db.save_record_qr(self.path, retained, f'{retained}.png')
        db.save_record_value(self.path, retained, second, 'New lab')
        self.assertIsNone(db.get_record(self.path, retained)['qr_filename'])
        db.save_record_qr(self.path, retained, f'{retained}.png')
        self.assertEqual(db.get_record(self.path, retained)['qr_filename'], f'{retained}.png')

    def test_startup_resets_previously_generated_qr_for_empty_records(self):
        record_id = db.create_record(self.path)
        with sqlite3.connect(self.path) as connection:
            connection.execute('UPDATE records SET qr_filename = ? WHERE record_id = ?',
                               (f'{record_id}.png', record_id))
        db.initialize_db(self.path)
        self.assertIsNone(db.get_record(self.path, record_id)['qr_filename'])

    def test_typed_values_and_last_updated_are_transactional(self):
        field_id = db.get_fields(self.path)[0]['id']
        db.save_field_name(self.path, field_id, 'Purchase', 'Date', 'DD/MM/YYYY')
        record_id = db.create_record(self.path)
        with patch.object(db, '_now', return_value='2026-09-13T10:00:00+00:00'):
            db.save_record_value(self.path, record_id, field_id, date(1994, 2, 1))
        before = db.get_record(self.path, record_id)
        self.assertEqual(before['values'][field_id], '1994-02-01')
        self.assertEqual(before['updated_at'], '2026-09-13T10:00:00+00:00')
        for invalid in ['1/2/94', '2025-02-29', '1994-2-1']:
            with self.assertRaises(ValueError):
                db.save_record_value(self.path, record_id, field_id, invalid)
        db.save_record_value(self.path, record_id, field_id, '1994-02-01')
        db.save_record_qr(self.path, record_id, 'record.png')
        self.assertEqual(db.get_record(self.path, record_id)['updated_at'], before['updated_at'])
        db.save_field_name(self.path, field_id, 'Purchase', 'Date', 'MM/DD/YYYY')
        self.assertEqual(db.get_record(self.path, record_id)['values'], before['values'])
        self.assertEqual(db.get_record(self.path, record_id)['updated_at'], before['updated_at'])
        db.save_record_value(self.path, record_id, field_id, None)
        self.assertIsNone(db.get_record(self.path, record_id)['qr_filename'])
        self.assertNotEqual(db.get_record(self.path, record_id)['updated_at'], before['updated_at'])
        db.save_field_name(self.path, field_id, 'Count', 'Text')
        for value in ['0', '-2.5', '123.456', '00123', 'ECG-001', 'hello']:
            db.save_record_value(self.path, record_id, field_id, value)
            self.assertEqual(db.get_record(self.path, record_id)['values'][field_id], str(value))
        with self.assertRaises(ValueError):
            db.save_field_name(self.path, field_id, 'Count', 'Other')
        db.remove_field(self.path, field_id)
        self.assertEqual(db.get_record(self.path, record_id)['values'], {})

    def test_schema_upgrade_preserves_text_and_does_not_invent_edit_history(self):
        path = Path(self.temp.name) / 'version1.db'
        with sqlite3.connect(path) as connection:
            connection.executescript("""
                CREATE TABLE custom_fields (id INTEGER PRIMARY KEY, sort_order INTEGER, field_name TEXT);
                INSERT INTO custom_fields VALUES (1, 1, 'Date');
                CREATE TABLE records (id INTEGER PRIMARY KEY, record_id TEXT UNIQUE, qr_filename TEXT, created_at TEXT);
                INSERT INTO records VALUES (1, 'REC-0001', NULL, '2020-01-01');
                CREATE TABLE record_values (record_id TEXT, field_id INTEGER, field_value TEXT, PRIMARY KEY(record_id, field_id));
                INSERT INTO record_values VALUES ('REC-0001', 1, '1/2/94');
                CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY);
                INSERT INTO schema_migrations VALUES (1);
            """)
        db.initialize_db(path)
        db.initialize_db(path)
        self.assertEqual(db.get_fields(path)[0]['field_type'], 'Text')
        self.assertEqual(db.get_record(path, 'REC-0001')['values'][1], '1/2/94')
        self.assertIsNone(db.get_record(path, 'REC-0001')['updated_at'])

    def test_numeric_field_upgrade_preserves_values_ids_qr_and_timestamp(self):
        first = db.get_fields(self.path)[0]['id']
        db.save_field_name(self.path, first, 'Count')
        db.add_field(self.path)
        second = db.get_fields(self.path)[1]['id']
        db.save_field_name(self.path, second, 'Date', 'Date', 'MM/DD/YYYY')
        record_id = db.create_record(self.path)
        db.save_record_value(self.path, record_id, first, '00123.00')
        db.save_record_qr(self.path, record_id, 'record.png')
        before = db.get_record(self.path, record_id)
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE custom_fields SET field_type = 'Number' WHERE id = ?", (first,))
            connection.execute('DELETE FROM schema_migrations WHERE version = 3')
        db.initialize_db(self.path)
        db.initialize_db(self.path)
        self.assertEqual(db.get_record(self.path, record_id), before)
        self.assertEqual(db.get_fields(self.path)[0]['field_type'], 'Text')
        self.assertEqual(db.get_fields(self.path)[1]['field_type'], 'Date')
        self.assertEqual(db.get_fields(self.path)[1]['date_format'], 'MM/DD/YYYY')
        db.save_record_value(self.path, record_id, first, '00123-A')
        self.assertEqual(db.get_record(self.path, record_id)['values'][first], '00123-A')


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'docs').mkdir()
        (self.root / 'docs' / 'USER_GUIDE.md').write_text(
            (ROOT / 'docs' / 'USER_GUIDE.md').read_text(encoding='utf-8'), encoding='utf-8')
        self.path = self.root / 'test.db'
        db.initialize_db(self.path)
        self.field_ids = []
        for index, name in enumerate(['Machine ID', 'beli', 'checkup']):
            if index:
                db.add_field(self.path)
            field_id = db.get_fields(self.path)[index]['id']
            db.save_field_name(self.path, field_id, name)
            self.field_ids.append(field_id)
        patcher = patch.object(db, 'DB_PATH', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        source = (ROOT / 'app.py').read_text().replace(
            'APP_DIR = Path(__file__).resolve().parent', f'APP_DIR = Path({str(self.root)!r})'
        )
        self.app = AppTest.from_string(source, default_timeout=30).run()

    def assert_clean(self):
        self.assertFalse(self.app.exception, str(self.app.exception))

    def test_admin_backup_and_confirmed_restore_clear_old_drafts(self):
        self.app.button(key='nav_Admin Panel').click().run()
        self.assertEqual([tab.label for tab in self.app.tabs], ['Field Settings', 'Backup & Restore'])
        self.app.button(key='create_backup').click().run()
        self.assert_clean()
        payload = self.app.session_state['prepared_backup']
        self.assertEqual(len(read_backup(payload)['fields']), 3)
        rid = db.create_record(self.path)
        self.app.text_input(key=f'field_name_{self.field_ids[0]}').set_value('draft').run()
        self.app.session_state['pending_restore'] = payload
        self.app.run()
        self.app.button(key='cancel_restore').click().run()
        self.assertIsNotNone(db.get_record(self.path, rid))
        self.assertEqual(self.app.text_input(key=f'field_name_{self.field_ids[0]}').value, 'draft')
        self.app.session_state['pending_restore'] = payload
        self.app.run()
        self.app.button(key='confirm_restore').click().run()
        self.assert_clean()
        self.assertIsNone(db.get_record(self.path, rid))
        self.assertEqual(self.app.text_input(key=f'field_name_{self.field_ids[0]}').value, 'Machine ID')
        self.assertTrue(self.app.success)
        copies = list((self.root / 'data' / 'backups').glob('*.zip'))
        self.assertEqual(len(copies), 1)
        self.assertEqual(read_backup(copies[0].read_bytes())['records'][0]['record_id'], rid)

    def test_restore_upload_validation_and_review_do_not_change_records(self):
        self.app.button(key='nav_Admin Panel').click().run()
        with patch('streamlit.file_uploader', return_value=SimpleNamespace(getvalue=lambda: b'bad zip')):
            self.app.run()
            self.assert_clean()
            self.assertTrue(self.app.error)
            self.assertFalse(any(button.key == 'review_restore' for button in self.app.button))
        payload = create_backup(self.path, self.root / 'qr_codes')
        rid = db.create_record(self.path)
        with patch('streamlit.file_uploader', return_value=SimpleNamespace(getvalue=lambda: payload)):
            self.app.run()
            self.app.button(key='review_restore').click().run()
            self.assert_clean()
            self.assertIsNotNone(db.get_record(self.path, rid))
            self.assertTrue(self.app.button(key='confirm_restore'))
            self.app.button(key='cancel_restore').click().run()
            self.assertIsNotNone(db.get_record(self.path, rid))
            self.assertFalse((self.root / 'data' / 'backups').exists())

    def manage(self):
        self.app.button(key='nav_Manage').click().run()
        self.assert_clean()

    def test_add_edit_unsaved_qr_done_search(self):
        self.manage()
        self.assertFalse(any(button.label == 'Del' for button in self.app.button))
        self.app.button(key='add_record').click().run()
        self.assertEqual(self.table_rows(), [
            ['Record ID', 'Machine ID', 'beli', 'checkup', 'QR Code'],
            ['REC-0001', '-', '-', '-', 'Not available'],
        ])
        table_html = next(item.value for item in self.app.markdown if '<table class="manage-records">' in item.value)
        self.assertIn('href="?record_id=REC-0001" target="_self"', table_html)
        self.app.query_params['record_id'] = 'REC-0001'
        self.app.run()
        self.assertEqual(self.app.title[0].value, 'Record Details')
        self.assertTrue(self.app.button(key='generate_qr').disabled)
        first, second, _ = self.field_ids
        self.app.text_input(key=f'value_REC-0001_{first}').set_value('M-100').run()
        self.assertTrue(self.app.button(key='generate_qr').disabled)
        self.assertTrue(any(item.value == 'Unsaved' for item in self.app.caption))
        # A click sent before the browser receives the disabled state must also be rejected.
        self.app.button(key='generate_qr').click().run()
        self.assertIsNone(db.get_record(self.path, 'REC-0001')['qr_filename'])
        self.app.button(key=f'save_value_{first}').click().run()
        self.assertFalse(self.app.button(key='generate_qr').disabled)
        self.app.text_input(key=f'value_REC-0001_{first}').set_value('M-101')
        self.app.text_input(key=f'value_REC-0001_{second}').set_value('2026').run()
        self.app.button(key=f'save_value_{second}').click().run()
        self.assertTrue(self.app.button(key='generate_qr').disabled)
        self.assertEqual(db.get_record(self.path, 'REC-0001')['values'][first], 'M-100')
        self.app.button(key=f'save_value_{first}').click().run()
        with patch('streamlit.download_button', wraps=st.download_button) as download:
            self.app.button(key='generate_qr').click().run()
        self.assert_clean()
        qr_path = self.root / 'qr_codes' / 'REC-0001.png'
        self.assertTrue(qr_path.is_file())
        self.assertEqual(download.call_args.kwargs['data'], qr_path.read_bytes())
        self.assertEqual(download.call_args.kwargs['file_name'], 'REC-0001.png')
        self.assertEqual(download.call_args.kwargs['mime'], 'image/png')
        self.assertEqual(download.call_args.kwargs['on_click'], 'ignore')
        original = qr_path.read_bytes()
        self.assertFalse(any(button.label == 'Regenerate QR' for button in self.app.button))
        self.app.text_input(key=f'value_REC-0001_{first}').set_value('M-102')
        self.app.button(key=f'save_value_{first}').click().run()
        self.assertEqual(qr_path.read_bytes(), original)
        self.app.button(key='detail_done').click().run()
        self.assert_clean()
        self.assertEqual(self.app.title[0].value, 'Manage')
        self.assertEqual(self.table_rows()[1], ['REC-0001', 'M-102', '2026', '-', 'Available'])
        for query in ['rec-0001', 'm-102', '2026']:
            self.app.text_input(key='manage_search').set_value(query).run()
            self.assertEqual(len(self.table_rows()) - 1, 1)
        self.app.text_input(key='manage_search').set_value('no match').run()
        self.assertEqual(len(self.table_rows()) - 1, 0)
        self.app.button(key='add_record').click().run()
        self.assertEqual(len(self.table_rows()) - 1, 2)
        self.assertEqual(self.app.text_input(key='manage_search').value, '')

    def test_home_uses_scanner_and_manage_handles_search(self):
        self.assertFalse(self.app.text_input)
        self.assertFalse(any(button.label == 'Open Record' for button in self.app.button))
        self.assertTrue(any(button.label == 'Scan QR' for button in self.app.button))
        with patch('scanner.qrcode_scanner', return_value=None) as scanner:
            self.app.button(key='home_scan_start').click().run()
            self.assert_clean()
            self.assertTrue(self.app.session_state['scanner_active'])
            self.assertEqual(scanner.call_count, 1)
            self.assertFalse(any(button.label == 'Scan QR' for button in self.app.button))
            self.app.button(key='home_scan_stop').click().run()
            self.assert_clean()
            self.assertFalse(self.app.session_state['scanner_active'])
            # Stop takes effect before rerendering, without restarting the camera.
            self.assertEqual(scanner.call_count, 1)
            self.assertTrue(self.app.button(key='home_scan_start'))
        self.manage()
        self.assertEqual(self.app.text_input(key='manage_search').label, 'Search records')

    def test_home_guide_opens_without_camera_and_returns_to_scanner(self):
        with patch('scanner.qrcode_scanner') as scanner:
            self.app.button(key='home_help').click().run()
            self.assert_clean()
            self.assertEqual(self.app.title[0].value, 'How to use')
            self.assertEqual(self.app.button(key='nav_Home').proto.type, 'primary')
            guide = '\n'.join(item.value for item in self.app.markdown)
            self.assertIn('## 1. Set up your fields', guide)
            self.assertIn('### Restore a backup', guide)
            scanner.assert_not_called()
            self.app.button(key='guide_back_home').click().run()
            self.assert_clean()
            self.assertEqual(self.app.session_state['current_page'], 'Home')
            self.assertTrue(self.app.button(key='home_scan_start'))
            scanner.assert_not_called()

    def test_calendar_requires_explicit_conversion_and_formats_saved_dates(self):
        first = self.field_ids[0]
        record_id = db.create_record(self.path)
        db.save_record_value(self.path, record_id, first, '1/2/94')
        before = db.get_record(self.path, record_id)
        self.app.button(key='nav_Admin Panel').click().run()
        self.app.selectbox(key=f'field_type_{first}').set_value('Date').run()
        self.assertFalse(self.app.selectbox(key=f'date_format_{first}').disabled)
        self.app.selectbox(key=f'date_format_{first}').set_value('MM/DD/YYYY').run()
        self.assertTrue(any(item.value == 'Unsaved' for item in self.app.caption))
        self.app.button(key=f'save_field_{first}').click().run()
        self.assertEqual(db.get_record(self.path, record_id), before)
        self.app.query_params['record_id'] = record_id
        self.app.run()
        calendar = self.app.date_input[0]
        self.assertIsNone(calendar.value)
        self.assertEqual(calendar.proto.format, 'MM/DD/YYYY')
        self.assertTrue(any('Previous saved text: 1/2/94' in item.value for item in self.app.caption))
        calendar.set_value(date(1994, 2, 1)).run()
        self.assertTrue(self.app.button(key='generate_qr').disabled)
        self.assertEqual(db.get_record(self.path, record_id), before)
        self.app.button(key=f'save_value_{first}').click().run()
        self.assertFalse(self.app.button(key='generate_qr').disabled)
        self.assertEqual(db.get_record(self.path, record_id)['values'][first], '1994-02-01')
        self.assertTrue(any('UTC' in item.value and 'Last updated' in item.value for item in self.app.caption))
        self.app.button(key='nav_Library').click().run()
        self.assertEqual(self.table_rows()[1][1], '02/01/1994')
        for query in ['02/01/1994', '1994-02-01']:
            self.app.text_input(key='library_search').set_value(query).run()
            self.assertEqual(len(self.table_rows()), 2)
        self.app.query_params['view_record'] = record_id
        self.app.run()
        self.assertTrue(any('02/01/1994' in item.value for item in self.app.markdown))
        self.assert_clean()

    def test_empty_calendar_text_zero_and_unsaved_date_navigation(self):
        first, second, _ = self.field_ids
        db.save_field_name(self.path, first, 'Date', 'Date', 'YYYY/MM/DD')
        db.save_field_name(self.path, second, 'Number', 'Text')
        record_id = db.create_record(self.path)
        self.app.query_params['record_id'] = record_id
        self.app.run()
        self.assertIsNone(self.app.date_input[0].value)
        self.assertFalse(self.app.number_input)
        self.assertTrue(self.app.button(key='generate_qr').disabled)
        self.app.text_input(key=f'value_{record_id}_{second}').set_value('0').run()
        self.app.button(key=f'save_value_{second}').click().run()
        self.assertFalse(self.app.button(key='generate_qr').disabled)
        self.app.date_input[0].set_value(date(2028, 2, 29))
        self.app.button(key='detail_done').click().run()
        self.assertEqual(self.app.session_state['pending_navigation'], 'Manage')
        self.app.button(key='leave_page').click().run()
        self.app._run()
        self.app.query_params['record_id'] = record_id
        self.app.run()
        self.assertIsNone(self.app.date_input[0].value)
        self.assertEqual(self.app.text_input(key=f'value_{record_id}_{second}').value, '0')
        self.assert_clean()

    def test_admin_offers_two_types_and_general_input_preserves_leading_zeroes(self):
        first = self.field_ids[0]
        self.app.button(key='nav_Admin Panel').click().run()
        selector = self.app.selectbox(key=f'field_type_{first}')
        self.assertEqual(selector.options, ['Text / Number', 'Date'])
        self.app.session_state[f'field_type_{first}'] = 'Number'
        # Simulate an old session without serializing through the new two-option widget.
        self.app._run()
        self.assertEqual(self.app.selectbox(key=f'field_type_{first}').value, 'Text')
        record_id = db.create_record(self.path)
        self.app.query_params['record_id'] = record_id
        self.app.run()
        for value in ['00123', 'ECG-001', '0']:
            self.app.text_input(key=f'value_{record_id}_{first}').set_value(value).run()
            self.app.button(key=f'save_value_{first}').click().run()
            self.assertEqual(db.get_record(self.path, record_id)['values'][first], value)
        self.assert_clean()

    def test_admin_type_and_format_drafts_are_not_saved_on_navigation(self):
        first = self.field_ids[0]
        self.app.button(key='nav_Admin Panel').click().run()
        self.app.selectbox(key=f'field_type_{first}').set_value('Date').run()
        self.app.selectbox(key=f'date_format_{first}').set_value('YYYY/MM/DD').run()
        self.app.button(key='nav_Library').click().run()
        self.assertEqual(self.app.session_state['pending_navigation'], 'Library')
        self.assertEqual(db.get_fields(self.path)[0]['field_type'], 'Text')
        self.app.button(key='leave_page').click().run()
        self.app._run()
        self.app.button(key='nav_Admin Panel').click().run()
        self.assertEqual(self.app.selectbox(key=f'field_type_{first}').value, 'Text')
        self.assertEqual(self.app.selectbox(key=f'date_format_{first}').value, 'DD/MM/YYYY')
        self.assert_clean()

    def test_legacy_value_can_be_cleared_explicitly(self):
        first = self.field_ids[0]
        record_id = db.create_record(self.path)
        db.save_record_value(self.path, record_id, first, 'not a date')
        db.save_field_name(self.path, first, 'Date', 'Date')
        self.app.query_params['record_id'] = record_id
        self.app.run()
        self.assertTrue(self.app.button(key=f'save_value_{first}').disabled)
        self.app.checkbox[0].check().run()
        self.assertEqual(db.get_record(self.path, record_id)['values'][first], 'not a date')
        self.app.button(key=f'save_value_{first}').click().run()
        self.assertEqual(db.get_record(self.path, record_id)['values'][first], '')
        self.assertFalse(self.app.checkbox)
        self.assert_clean()

    def test_label_dialog_download_preserves_record_and_qr(self):
        record_id = db.create_record(self.path)
        db.save_record_value(self.path, record_id, self.field_ids[0], 'Machine')
        filename = generate_qr_code(record_id, self.root / 'qr_codes')
        db.save_record_qr(self.path, record_id, filename)
        before = db.get_record(self.path, record_id)
        self.app.query_params['record_id'] = record_id
        self.app.run()
        with patch('streamlit.download_button', wraps=st.download_button) as download:
            self.app.button(key='print_qr_label').click().run()
        pdf_call = next(call for call in download.call_args_list if call.kwargs.get('mime') == 'application/pdf')
        document = PdfReader(BytesIO(pdf_call.kwargs['data']))
        self.assertEqual(document.pages[0].extract_text(), record_id)
        self.app.selectbox(key='label_size').set_value(40).run()
        self.assertEqual(db.get_record(self.path, record_id), before)
        self.assert_clean()

    def test_library_search_and_record_view_preserve_saved_data(self):
        record_id = db.create_record(self.path)
        db.create_record(self.path)
        value = '<script>alert("test")</script>\nMouse'
        db.save_record_value(self.path, record_id, self.field_ids[0], value)
        before = db.get_records(self.path)
        self.app.button(key='nav_Library').click().run()
        self.assertEqual(self.app.title[0].value, 'Library')
        self.assertEqual(len(self.table_rows()), 3)
        self.assertFalse(any(button.label in ['Add', 'Del', 'Save', 'Remove'] for button in self.app.button))
        for query in ['REC-0001', 'mouse']:
            self.app.text_input(key='library_search').set_value(query).run()
            self.assertEqual(len(self.table_rows()), 2)
        table = next(item.value for item in self.app.markdown if '<table class="manage-records">' in item.value)
        self.assertIn('href="?view_record=REC-0001" target="_self"', table)
        self.app.query_params['view_record'] = record_id
        self.app.run()
        self.assertEqual(self.app.session_state['current_page'], 'Library Record')
        self.assertEqual(self.app.button(key='nav_Library').proto.type, 'primary')
        self.assertFalse(self.app.text_input)
        self.assertFalse(self.app.get('download_button'))
        self.assertFalse(any(button.label in ['Save', 'Add', 'Del', 'Remove', 'Generate QR'] for button in self.app.button))
        details = next(item.value for item in self.app.markdown if '<table class="library-details">' in item.value)
        self.assertIn('&lt;script&gt;', details)
        self.assertIn('Machine ID', details)
        self.assertIn('<td>-</td>', details)
        self.assertIn('Not available', [item.value for item in self.app.caption])
        self.app.button(key='library_back').click().run()
        self.assertEqual(self.app.session_state['current_page'], 'Library')
        self.assertFalse(self.app.query_params)
        self.assertEqual(db.get_records(self.path), before)
        self.manage()
        self.assertTrue(any(button.label == 'Add' for button in self.app.button))
        self.assert_clean()

    def test_library_manage_opens_same_record_and_keeps_edit_route_after_save(self):
        record_id = db.create_record(self.path)
        field_id = self.field_ids[0]
        db.save_record_value(self.path, record_id, field_id, 'Original machine')
        self.app.query_params['view_record'] = record_id
        self.app.run()
        self.app.button(key='library_manage').click().run()
        self.assertEqual(self.app.title[0].value, 'Record Details')
        self.assertEqual(self.app.session_state['selected_record_id'], record_id)
        self.assertNotIn('view_record', self.app.query_params)
        self.assertEqual(self.app.query_params['record_id'], [record_id])
        self.assertEqual(self.app.button(key='nav_Manage').proto.type, 'primary')
        entry = self.app.text_input(key=f'value_{record_id}_{field_id}')
        self.assertEqual(entry.value, 'Original machine')
        entry.set_value('Updated machine').run()
        self.app.button(key=f'save_value_{field_id}').click().run()
        self.assertEqual(self.app.title[0].value, 'Record Details')
        self.assertEqual(db.get_record(self.path, record_id)['values'][field_id], 'Updated machine')
        self.assert_clean()

    def test_library_record_handles_removed_fields_and_deleted_record(self):
        record_id = db.create_record(self.path)
        for field_id in self.field_ids:
            db.remove_field(self.path, field_id)
        self.app.query_params['view_record'] = record_id
        self.app.run()
        self.assertIn('No field information', self.app.info[0].value)
        db.delete_records(self.path, [record_id])
        self.app.run()
        self.assertTrue(any('no longer exists' in item.value for item in self.app.warning))
        self.assertFalse(any(button.key == 'library_manage' for button in self.app.button))
        self.app.button(key='library_back').click().run()
        self.assertEqual(self.app.session_state['current_page'], 'Library')
        self.assert_clean()

    def table_rows(self):
        class TableParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows = []
                self.in_cell = False

            def handle_starttag(self, tag, attrs):
                if tag == 'tr':
                    self.rows.append([])
                elif tag in ('th', 'td'):
                    self.rows[-1].append('')
                    self.in_cell = True

            def handle_endtag(self, tag):
                if tag in ('th', 'td'):
                    self.in_cell = False

            def handle_data(self, data):
                if self.in_cell:
                    self.rows[-1][-1] += data

        parser = TableParser()
        parser.feed(next(item.value for item in self.app.markdown if '<table class="manage-records">' in item.value))
        return parser.rows

    def test_delete_yes_no_and_empty_results(self):
        self.manage()
        for _ in range(2):
            self.app.button(key='add_record').click().run()
        self.assertFalse(self.app.checkbox)
        self.assertEqual([button.key for button in self.app.button if button.label == 'Del'],
                         ['delete_REC-0001', 'delete_REC-0002'])
        self.app.button(key='delete_REC-0001').click().run()
        self.assertIsNotNone(db.get_record(self.path, 'REC-0001'))
        self.app.button(key='cancel_delete').click().run()
        self.assertEqual(len(db.get_records(self.path)), 2)
        for record_id in ['REC-0001', 'REC-0002']:
            self.app.button(key=f'delete_{record_id}').click().run()
            self.app.button(key='confirm_delete').click().run()
            self.assertIsNone(db.get_record(self.path, record_id))
            # AppTest retains stale nodes when a dialog rerun shortens a list.
            self.app.run()
        self.assert_clean()
        self.assertEqual(db.get_records(self.path), [])
        self.assertFalse(any(button.label == 'Del' for button in self.app.button))
        self.app.button(key='add_record').click().run()
        self.assertEqual(db.get_records(self.path)[0]['record_id'], 'REC-0003')
        self.app.text_input(key='manage_search').set_value('missing').run()
        self.assertFalse(any(button.label == 'Del' for button in self.app.button))

    def test_row_delete_popup_targets_only_clicked_record(self):
        self.manage()
        for _ in range(3):
            self.app.button(key='add_record').click().run()
        # A row's external Del button must only target that record.
        self.app.button(key='delete_REC-0003').click().run()
        self.assert_clean()
        self.assertEqual(len(self.app.get('dialog')), 1)
        self.assertEqual(self.app.session_state['pending_delete'], ['REC-0003'])
        self.assertEqual(len(db.get_records(self.path)), 3)
        self.app.button(key='cancel_delete').click().run()
        self.assertEqual(len(db.get_records(self.path)), 3)
        self.assertNotIn('pending_delete', self.app.session_state.filtered_state)
        # The same row can be clicked again after cancellation, including through search.
        self.app.text_input(key='manage_search').set_value('REC-0003').run()
        self.app.button(key='delete_REC-0003').click().run()
        self.assertEqual(self.app.session_state['pending_delete'], ['REC-0003'])
        self.app.button(key='confirm_delete').click().run()
        self.assert_clean()
        self.assertIsNone(db.get_record(self.path, 'REC-0003'))
        self.assertEqual([row['record_id'] for row in db.get_records(self.path)], ['REC-0001', 'REC-0002'])
        self.assertNotIn('pending_delete', self.app.session_state.filtered_state)

    def test_admin_saves_only_clicked_field_and_stable_removal(self):
        self.app.button(key='nav_Admin Panel').click().run()
        first, second, third = self.field_ids
        self.assertTrue(any(button.key == f'remove_field_{first}' for button in self.app.button))
        self.app.text_input(key=f'field_name_{first}').set_value('Machine')
        self.app.text_input(key=f'field_name_{second}').set_value('Purchase')
        self.app.button(key=f'save_field_{first}').click().run()
        self.assertEqual([field['field_name'] for field in db.get_fields(self.path)], ['Machine', 'beli', 'checkup'])
        self.app.button(key='add_field').click().run()
        self.assertEqual(db.get_fields(self.path)[1]['field_name'], 'beli')
        self.app.button(key=f'remove_field_{second}').click().run()
        self.app.button(key='confirm_remove_field').click().run()
        self.app.run()
        self.assertEqual(self.app.text_input(key=f'field_name_{third}').value, 'checkup')
        for _ in range(3):
            self.app.button(key='add_field').click().run()
        self.assertTrue(self.app.button(key='add_field').disabled)
        self.assertEqual(len(self.app.text_input), 6)
        self.assert_clean()

    def test_detail_navigation_protects_unsaved_changes(self):
        record_id = db.create_record(self.path)
        self.app.query_params['record_id'] = record_id
        self.app.run()
        first = self.field_ids[0]
        key = f'value_{record_id}_{first}'
        self.assertTrue(self.app.button(key=f'save_value_{first}').disabled)
        self.assertEqual(self.app.button(key='nav_Manage').proto.type, 'primary')
        self.app.text_input(key=key).set_value('Draft')
        self.app.button(key='detail_done').click().run()
        self.assertEqual(self.app.title[0].value, 'Record Details')
        self.assertEqual(self.app.session_state['pending_navigation'], 'Manage')
        self.assertEqual(self.app.text_input(key=key).value, 'Draft')
        self.assertEqual(db.get_record(self.path, record_id)['values'], {})
        self.app.button(key='stay_on_page').click().run()
        self.assertEqual(self.app.text_input(key=key).value, 'Draft')
        self.app.run()
        self.app.button(key='detail_done').click().run()
        self.app.button(key='leave_page').click().run()
        self.assertEqual(self.app.title[0].value, 'Manage')
        self.assertEqual(self.app.query_params, {})
        # Rebuild AppTest's tree after a dialog changes pages; old input nodes may remain.
        self.app._run()
        self.app.query_params['record_id'] = record_id
        self.app.run()
        self.assertEqual(self.app.text_input(key=key).value, '')
        self.app.text_input(key=key).set_value('Saved value')
        self.app.button(key=f'save_value_{first}').click().run()
        self.assertTrue(any(item.value == 'Saved ✓' for item in self.app.caption))
        self.assertTrue(self.app.button(key=f'save_value_{first}').disabled)
        self.app.button(key='nav_Home').click().run()
        self.assertEqual(self.app.session_state['current_page'], 'Home')
        self.assertNotIn('pending_navigation', self.app.session_state.filtered_state)
        self.assertEqual(db.get_record(self.path, record_id)['values'][first], 'Saved value')
        self.assert_clean()

    def test_admin_navigation_and_save_feedback(self):
        self.app.button(key='nav_Admin Panel').click().run()
        first = self.field_ids[0]
        key = f'field_name_{first}'
        self.assertEqual(self.app.button(key='nav_Admin Panel').proto.type, 'primary')
        self.assertTrue(self.app.button(key=f'save_field_{first}').disabled)
        self.app.text_input(key=key).set_value('Draft')
        self.app.button(key='nav_Manage').click().run()
        self.assertEqual(self.app.title[0].value, 'Admin Panel')
        self.assertEqual(self.app.text_input(key=key).value, 'Draft')
        self.app.button(key='stay_on_page').click().run()
        self.app.run()
        self.app.button(key=f'save_field_{first}').click().run()
        self.assertTrue(any(item.value == 'Saved ✓' for item in self.app.caption))
        self.assertTrue(self.app.button(key=f'save_field_{first}').disabled)
        self.app.text_input(key=key).set_value('Abandoned')
        self.app.button(key='nav_Manage').click().run()
        self.app.button(key='leave_page').click().run()
        self.app._run()
        self.app.button(key='nav_Admin Panel').click().run()
        self.assertEqual(self.app.text_input(key=key).value, 'Draft')
        self.assertFalse(self.app.warning)
        self.assert_clean()

    def test_remove_field_requires_confirmation_and_preserves_other_values(self):
        record_id = db.create_record(self.path)
        first, second, _ = self.field_ids
        db.save_record_value(self.path, record_id, first, 'Keep this')
        db.save_record_value(self.path, record_id, second, 'Remove this')
        self.app.button(key='nav_Admin Panel').click().run()
        self.app.button(key=f'remove_field_{second}').click().run()
        self.assertEqual(len(self.app.get('dialog')), 1)
        self.assertIn('every record', self.app.warning[0].value)
        self.assertEqual(db.get_record(self.path, record_id)['values'][second], 'Remove this')
        self.app.button(key='cancel_remove_field').click().run()
        self.app.run()
        self.assertEqual(len(db.get_fields(self.path)), 3)
        self.app.button(key=f'remove_field_{second}').click().run()
        self.app.button(key='confirm_remove_field').click().run()
        self.app.run()
        self.assertEqual(len(db.get_fields(self.path)), 2)
        self.assertEqual(db.get_record(self.path, record_id)['values'], {first: 'Keep this'})
        self.assert_clean()

    def test_remove_first_and_last_fields_then_add_again(self):
        record_id = db.create_record(self.path)
        db.save_record_value(self.path, record_id, self.field_ids[0], 'Old value')
        db.save_record_qr(self.path, record_id, f'{record_id}.png')
        self.app.button(key='nav_Admin Panel').click().run()
        first = self.field_ids[0]
        self.app.button(key=f'remove_field_{first}').click().run()
        self.app.button(key='cancel_remove_field').click().run()
        self.app._run()
        self.assertEqual(len(db.get_fields(self.path)), 3)
        for field_id in self.field_ids:
            self.app.button(key=f'remove_field_{field_id}').click().run()
            self.app.button(key='confirm_remove_field').click().run()
            self.app._run()
        self.assertEqual(db.get_fields(self.path), [])
        self.assertFalse(self.app.text_input)
        db.initialize_db(self.path)
        self.assertEqual(db.get_fields(self.path), [])
        record = db.get_record(self.path, record_id)
        self.assertEqual(record['values'], {})
        self.assertEqual(record['record_id'], record_id)
        self.assertIsNone(record['qr_filename'])
        self.app.button(key='add_field').click().run()
        new_field = db.get_fields(self.path)[0]
        self.assertGreater(new_field['id'], max(self.field_ids))
        self.assertEqual(self.app.text_input(key=f"field_name_{new_field['id']}").value, '')
        self.assertFalse(self.app.button(key=f"remove_field_{new_field['id']}").disabled)
        self.assert_clean()

    def test_empty_record_hides_qr_and_requires_explicit_generation_again(self):
        record_id = db.create_record(self.path)
        first = self.field_ids[0]
        db.save_record_value(self.path, record_id, first, 'Machine')
        filename = generate_qr_code(record_id, self.root / 'qr_codes')
        db.save_record_qr(self.path, record_id, filename)
        self.app.query_params['record_id'] = record_id
        self.app.run()
        self.assertEqual(len(self.app.get('download_button')), 1)
        key = f'value_{record_id}_{first}'
        self.app.text_input(key=key).set_value('').run()
        self.assertEqual(db.get_record(self.path, record_id)['qr_filename'], filename)
        self.app.button(key=f'save_value_{first}').click().run()
        self.assertIsNone(db.get_record(self.path, record_id)['qr_filename'])
        self.assertFalse(self.app.get('download_button'))
        self.assertFalse(self.app.get('imgs'))
        self.assertTrue(self.app.button(key='generate_qr').disabled)
        self.app.button(key='detail_done').click().run()
        self.assertEqual(self.table_rows()[1][-1], 'Not available')
        self.app.query_params['record_id'] = record_id
        self.app.run()
        self.app.text_input(key=key).set_value('New machine')
        self.app.button(key=f'save_value_{first}').click().run()
        self.assertFalse(self.app.get('download_button'))
        self.assertFalse(self.app.button(key='generate_qr').disabled)
        self.app.button(key='generate_qr').click().run()
        self.assertEqual(len(self.app.get('download_button')), 1)
        self.assertEqual(db.get_record(self.path, record_id)['record_id'], record_id)
        self.assert_clean()

    def test_app_scanner_rejects_reset_qr_until_generated_again(self):
        record_id = db.create_record(self.path)
        first = self.field_ids[0]
        db.save_record_value(self.path, record_id, first, 'Machine')
        filename = generate_qr_code(record_id, self.root / 'qr_codes')
        db.save_record_qr(self.path, record_id, filename)
        db.save_record_value(self.path, record_id, first, '')
        scanner = SimpleNamespace(qrcode_scanner=lambda **kwargs: record_id)
        with patch.dict('sys.modules', {'scanner': scanner}):
            next(button for button in self.app.button if button.label == 'Scan QR').click().run()
            self.assertEqual(self.app.session_state['current_page'], 'Home')
            self.assertIn('not active', self.app.warning[0].value)
            db.save_record_value(self.path, record_id, first, 'Refilled')
            self.app.run()
            self.assertEqual(self.app.session_state['current_page'], 'Home')
            self.assertIn('not active', self.app.warning[0].value)
            db.save_record_qr(self.path, record_id, filename)
            self.app.run()
            self.assertEqual(self.app.title[0].value, 'Library')
            self.assertEqual(self.app.session_state['current_page'], 'Library Record')
            self.assertFalse(self.app.text_input)
            self.assertFalse(self.app.get('download_button'))
            self.assertEqual(len(self.app.get('imgs')), 1)
            self.assertFalse(self.app.session_state['scanner_active'])
            self.assertTrue(any('Refilled' in item.value for item in self.app.markdown))
        self.assert_clean()


if __name__ == '__main__':
    unittest.main()
