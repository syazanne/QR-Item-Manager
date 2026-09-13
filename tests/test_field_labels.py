import unittest
from datetime import date
from io import BytesIO
from unittest.mock import patch

import qrcode
from pypdf import PdfReader
from pypdf.generic import IndirectObject

from field_utils import display_value, parse_saved_date, normalize_value
from label_utils import LABEL_SIZES, label_pdf, label_print_html


class FieldFormatTests(unittest.TestCase):
    def test_formats_change_presentation_without_guessing_legacy_dates(self):
        for layout, expected in [('DD/MM/YYYY', '06/05/2027'), ('MM/DD/YYYY', '05/06/2027'), ('YYYY/MM/DD', '2027/05/06')]:
            field = {'field_type': 'Date', 'date_format': layout}
            self.assertEqual(display_value(field, '2027-05-06'), expected)
            self.assertEqual(display_value(field, '1/2/94'), '1/2/94')
            self.assertEqual(display_value(field, ''), '-')
        self.assertIsNone(parse_saved_date('1/2/94'))
        self.assertIsNone(parse_saved_date('2027-02-29'))
        self.assertEqual(normalize_value('Date', date(2028, 2, 29)), '2028-02-29')


class LabelTests(unittest.TestCase):
    def test_pdf_sizes_readable_id_and_indirect_content_stream(self):
        for size in LABEL_SIZES:
            with self.subTest(size=size):
                pdf = PdfReader(BytesIO(label_pdf('REC-0008', size)), strict=True)
                self.assertEqual(len(pdf.pages), 1)
                page = pdf.pages[0]
                self.assertAlmostEqual(float(page.mediabox.width), size * 72 / 25.4, places=4)
                self.assertAlmostEqual(float(page.mediabox.height), size * 72 / 25.4, places=4)
                self.assertEqual(page.extract_text(), 'REC-0008')
                # Stream objects must be indirect for native PDF viewers/printers.
                self.assertIsInstance(page.raw_get('/Contents'), IndirectObject)

    def test_printed_qr_contains_only_id(self):
        qr = qrcode.QRCode()
        with patch('label_utils.qrcode.QRCode', return_value=qr), patch.object(qr, 'add_data', wraps=qr.add_data) as add_data:
            label_pdf('REC-0010')
        add_data.assert_called_once_with('REC-0010')
        preview = label_print_html('REC-0010', b'png', 50)
        self.assertIn('window.print()', preview)
        self.assertIn('@page { size: 50mm 50mm; margin: 0; }', preview)
        self.assertIn('data:image/png;base64,', preview)
        self.assertNotIn('http', preview)
        for record_id, size in [('<script>', 50), ('REC-0008', 200)]:
            with self.assertRaises(ValueError):
                label_pdf(record_id, size)
            with self.assertRaises(ValueError):
                label_print_html(record_id, b'', size)


if __name__ == '__main__':
    unittest.main()
