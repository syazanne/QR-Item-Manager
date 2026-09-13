"""Local camera component with a visible preview and a square QR scan area."""
from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent


def qrcode_scanner(key: str = "record_qr_scanner") -> str | None:
    try:
        package = distribution("streamlit-qrcode-scanner")
    except PackageNotFoundError as exc:
        raise ImportError("Install streamlit-qrcode-scanner to enable the camera scanner.") from exc
    # Reuse the installed package's local decoder, while owning the preview UI here.
    decoder = Path(package.locate_file("streamlit_qrcode_scanner/frontend/html5-qrcode.min.js"))
    if not decoder.is_file():
        raise ImportError("The QR decoder is missing. Reinstall streamlit-qrcode-scanner.")
    bundle = APP_DIR / "data" / "scanner_component"
    bundle.mkdir(parents=True, exist_ok=True)
    sources = [*sorted((APP_DIR / "scanner_frontend").glob("*")), decoder]
    assets = {source.name: source.read_bytes() for source in sources if source.is_file()}
    revision = hashlib.sha256(b"".join(assets.values())).hexdigest()[:12]
    for name, content in assets.items():
        destination = bundle / name
        if name == "index.html":
            for asset in ("main.js", "style.css", "html5-qrcode.min.js"):
                content = content.replace(f'"{asset}"'.encode(), f'"{asset}?v={revision}"'.encode())
        if not destination.is_file() or destination.read_bytes() != content:
            destination.write_bytes(content)
    component = components.declare_component("qr_camera", path=str(bundle))
    return component(key=f"{key}_{revision}", default=None)
