from __future__ import annotations

from pathlib import Path
import re

import qrcode


def generate_qr_code(record_id: str, output_dir: Path) -> str:
    """Save a QR containing only the permanent Record ID, never a URL or values."""
    clean_record_id = (record_id or "").strip()
    if not re.fullmatch(r"REC-[0-9]{4,}", clean_record_id):
        raise ValueError("A valid Record ID is required to generate a QR code.")

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{clean_record_id}.png"
    target_path = output_dir / filename

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(clean_record_id)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    image.save(target_path)
    return filename
