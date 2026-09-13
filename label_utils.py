"""Printable QR labels: a vector PDF and an isolated browser print preview."""
from __future__ import annotations

import base64
from io import BytesIO
import re

import qrcode
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

LABEL_SIZES = (40, 50, 60)


def validate_label(record_id: str, size_mm: int) -> None:
    if not re.fullmatch(r"REC-[0-9]{4,}", record_id) or size_mm not in LABEL_SIZES:
        raise ValueError("Choose a valid record and label size.")


def label_pdf(record_id: str, size_mm: int = 50) -> bytes:
    """Build a square label at physical print dimensions, with a vector QR."""
    validate_label(record_id, size_mm)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    qr.add_data(record_id)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    mm = 72 / 25.4
    page_size = size_mm * mm
    qr_size = (size_mm - 8) * mm
    unit = qr_size / len(matrix)
    left, bottom = 4 * mm, 7 * mm
    commands = ["1 g", f"0 0 {page_size:.5f} {page_size:.5f} re f", "0 g"]
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                commands.append(f"{left + x * unit:.5f} {bottom + (len(matrix) - y - 1) * unit:.5f} {unit:.5f} {unit:.5f} re f")
    font_size = min(10, (page_size - 8 * mm) / (len(record_id) * 0.6))
    text_x = (page_size - len(record_id) * font_size * 0.6) / 2
    commands.append(f"BT /F1 {font_size:.3f} Tf {text_x:.3f} {4 * mm:.3f} Td ({record_id}) Tj ET")
    writer = PdfWriter()
    page = writer.add_blank_page(width=page_size, height=page_size)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Courier")})})})
    content = DecodedStreamObject()
    content.set_data("\n".join(commands).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def label_print_html(record_id: str, png: bytes, size_mm: int = 50) -> str:
    validate_label(record_id, size_mm)
    image = base64.b64encode(png).decode("ascii")
    return f"""<!doctype html><html><head><style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font: 14px system-ui, sans-serif; }}
        .label {{ width: {size_mm}mm; height: {size_mm}mm; background: white; color: black;
            display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        img {{ width: {size_mm - 8}mm; height: {size_mm - 8}mm; image-rendering: pixelated; }}
        .record-id {{ font: 10pt monospace; }}
        button {{ margin-top: 12px; padding: 8px 14px; border: 1px solid #d9dfe8;
            border-radius: 6px; background: white; cursor: pointer; font: inherit; }}
        @page {{ size: {size_mm}mm {size_mm}mm; margin: 0; }}
        @media print {{ button {{ display: none; }} body {{ width: {size_mm}mm; height: {size_mm}mm; }} }}
        </style></head><body>
        <div class="label"><img src="data:image/png;base64,{image}" alt="QR code for {record_id}">
        <div class="record-id">{record_id}</div></div>
        <button type="button" onclick="window.print()">Print label</button>
        </body></html>"""
