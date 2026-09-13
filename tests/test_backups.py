import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import backup_utils as backup
import database as db
from qr_utils import generate_qr_code


def rewrite_zip(payload, change=None, extra=None):
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    if change:
        manifest = json.loads(files['manifest.json'])
        change(manifest)
        files['manifest.json'] = json.dumps(manifest).encode()
    files.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


class BackupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path, self.qrs, self.safety = self.root / 'test.db', self.root / 'qr_codes', self.root / 'backups'
        db.initialize_db(self.path)
        self.field = db.get_fields(self.path)[0]['id']
        db.save_field_name(self.path, self.field, 'machineID')
        self.rid = db.create_record(self.path)
        db.save_record_value(self.path, self.rid, self.field, '001-ECG')
        db.save_record_qr(self.path, self.rid, generate_qr_code(self.rid, self.qrs))
        db.add_field(self.path)
        date_field = db.get_fields(self.path)[1]['id']
        db.save_field_name(self.path, date_field, 'check', 'Text')
        db.save_record_value(self.path, self.rid, date_field, '1/2/94')
        db.save_field_name(self.path, date_field, 'check', 'Date', 'YYYY/MM/DD')

    def snapshot(self):
        return db.get_fields(self.path), db.get_records(self.path)

    def test_portable_round_trip_preserves_values_dates_timestamps_and_ids(self):
        # The high-water mark must survive even when the most recent record was deleted.
        deleted = db.create_record(self.path)
        db.delete_records(self.path, [deleted])
        original_fields, original_records = self.snapshot()
        payload = backup.create_backup(self.path, self.qrs)
        target, target_qrs = self.root / 'new.db', self.root / 'new_qrs'
        db.initialize_db(target)
        safety = backup.restore_backup(payload, target, target_qrs, self.safety)
        self.assertTrue(safety.is_file())
        self.assertEqual(db.get_fields(target), original_fields)
        restored = db.get_records(target)
        self.assertEqual({k: v for k, v in restored[0].items() if k != 'qr_filename'},
                         {k: v for k, v in original_records[0].items() if k != 'qr_filename'})
        self.assertEqual((target_qrs / restored[0]['qr_filename']).read_bytes(), (self.qrs / f'{self.rid}.png').read_bytes())
        self.assertEqual(db.create_record(target), 'REC-0003')
        # Restored images are included in subsequent portable backups too.
        self.assertEqual(len(backup.read_backup(backup.create_backup(target, target_qrs))['images']), 1)

    def test_safety_backup_recovers_replaced_data_and_never_reuses_newer_ids(self):
        old = backup.create_backup(self.path, self.qrs)
        db.save_record_value(self.path, self.rid, self.field, 'updated value')
        newer = db.create_record(self.path)
        safety = backup.restore_backup(old, self.path, self.qrs, self.safety)
        self.assertEqual(db.get_record(self.path, self.rid)['values'][self.field], '001-ECG')
        self.assertIsNone(db.get_record(self.path, newer))
        self.assertEqual(db.create_record(self.path), 'REC-0003')
        backup.restore_backup(safety.read_bytes(), self.path, self.qrs, self.safety)
        self.assertEqual(db.get_record(self.path, self.rid)['values'][self.field], 'updated value')
        self.assertIsNotNone(db.get_record(self.path, newer))

    def test_empty_backup_does_not_reseed_fields_or_reactivate_qr(self):
        for field in db.get_fields(self.path):
            db.remove_field(self.path, field['id'])
        db.delete_records(self.path, [self.rid])
        payload = backup.create_backup(self.path, self.qrs)
        db.add_field(self.path)
        backup.restore_backup(payload, self.path, self.qrs, self.safety)
        db.initialize_db(self.path)
        self.assertEqual(self.snapshot(), ([], []))
        self.assertEqual(db.create_record(self.path), 'REC-0002')

    def test_missing_qr_is_reported_and_remains_unavailable(self):
        (self.qrs / f'{self.rid}.png').unlink()
        payload = backup.create_backup(self.path, self.qrs)
        summary = backup.read_backup(payload)
        self.assertEqual(summary['missing_qr_images'], [self.rid])
        backup.restore_backup(payload, self.path, self.qrs, self.safety)
        self.assertIsNone(db.get_record(self.path, self.rid)['qr_filename'])

    def test_app_rename_keeps_old_backups_restorable(self):
        payload = backup.create_backup(self.path, self.qrs)
        self.assertEqual(backup.read_backup(payload)['application'], 'QR Item Manager')
        legacy = rewrite_zip(payload, lambda m: m.update(application='QR-MedTech'))
        db.save_record_value(self.path, self.rid, self.field, 'changed')
        backup.restore_backup(legacy, self.path, self.qrs, self.safety)
        self.assertEqual(db.get_record(self.path, self.rid)['values'][self.field], '001-ECG')

    def test_reject_invalid_archives_before_mutation(self):
        good = backup.create_backup(self.path, self.qrs)
        before = self.snapshot()
        changes = [
            lambda m: m.update(version=999),
            lambda m: m['records'][0].update(record_id='REC-0999'),
            lambda m: m['records'].append(dict(m['records'][0])),
            lambda m: m['values'][0].update(field_id=999),
            lambda m: m['fields'][0].update(field_type='SQL'),
            lambda m: m['records'][0].update(updated_at='not a time'),
            lambda m: m['records'][0].update(qr_filename='../../outside.png'),
            lambda m: m['sequences'].update(records=0),
            lambda m: m['values'][0].update(field_value=[]),
        ]
        bad = [b'not zip', good[:40]] + [rewrite_zip(good, change) for change in changes]
        bad += [rewrite_zip(good, extra={'../../outside.txt': b'no'}),
                rewrite_zip(good, extra={f'qr_codes/{self.rid}.png': b'corrupted'})]
        for payload in bad:
            with self.subTest(payload=payload[:20]):
                with self.assertRaises(backup.BackupError):
                    backup.restore_backup(payload, self.path, self.qrs, self.safety)
                self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.safety.exists())

    def test_oversize_duplicate_entries_rejected(self):
        good = backup.create_backup(self.path, self.qrs)
        with patch.object(backup, 'MAX_BYTES', 20):
            with self.assertRaises(backup.BackupError):
                backup.read_backup(good)
        out = io.BytesIO(good)
        with zipfile.ZipFile(out, 'a') as archive:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr('manifest.json', '{}')
        with self.assertRaises(backup.BackupError):
            backup.read_backup(out.getvalue())

    def test_database_failure_rolls_back_records_and_cleans_new_qrs(self):
        payload = backup.create_backup(self.path, self.qrs)
        db.save_record_value(self.path, self.rid, self.field, 'keep me')
        before = self.snapshot()
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TRIGGER reject_restore BEFORE INSERT ON records BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            backup.restore_backup(payload, self.path, self.qrs, self.safety)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue((self.qrs / f'{self.rid}.png').is_file())
        self.assertFalse(list(self.qrs.glob('restore_*')))
        self.assertEqual(len(list(self.safety.glob('*.zip'))), 1)

    def test_safety_backup_failure_aborts_without_replacing_data(self):
        payload = backup.create_backup(self.path, self.qrs)
        before = self.snapshot()
        self.safety.write_text('not a directory')
        with self.assertRaises(OSError):
            backup.restore_backup(payload, self.path, self.qrs, self.safety)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(list(self.qrs.glob('restore_*')))


if __name__ == '__main__':
    unittest.main()
