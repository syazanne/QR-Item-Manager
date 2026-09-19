"""Local camera component with a visible preview and a square QR scan area."""
from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent


def qrcode_scanner(key: str = "record_qr_scanner") -> str | None:
    frontend = APP_DIR / "scanner_frontend"
    if not (frontend / "vendor" / "jsQR.js").is_file():
        raise ImportError("The bundled QR decoder is missing. Restore scanner_frontend/vendor/jsQR.js.")
    # Separate from the old generated bundle so no html5-qrcode assets are served.
    bundle = APP_DIR / "data" / "scanner_component_jsqr"
    bundle.mkdir(parents=True, exist_ok=True)
    assets = {source.relative_to(frontend).as_posix(): source.read_bytes()
              for source in sorted(frontend.rglob("*")) if source.is_file()}
    revision = hashlib.sha256(b"".join(name.encode() + b"\0" + content
                                      for name, content in assets.items())).hexdigest()[:12]
    for name, content in assets.items():
        destination = bundle / name
        if name == "index.html":
            for asset in ("main.js", "style.css", "vendor/jsQR.js"):
                content = content.replace(f'"{asset}"'.encode(), f'"{asset}?v={revision}"'.encode())
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or destination.read_bytes() != content:
            destination.write_bytes(content)
    component = components.declare_component("qr_camera_jsqr", path=str(bundle))
    return component(key=f"{key}_{revision}", default=None)
