from __future__ import annotations

from pathlib import Path

import qrcode


def generate_qr_code(machine_id: str, output_dir: Path) -> str:
    """Generate a QR code that stores only the equipment ID and save it locally."""
    clean_machine_id = (machine_id or "").strip()
    if not clean_machine_id:
        raise ValueError("Machine ID is required to generate a QR code.")

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{clean_machine_id}.png"
    target_path = output_dir / filename

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(clean_machine_id)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    image.save(target_path)
    return filename
