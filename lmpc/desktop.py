"""Portable localhost launcher used by the Windows release bundle.

The executable deliberately binds to loopback, uses the in-memory scan repository, and
stores immutable image/report objects below the current user's application-data folder.
It is a demo and field-test package: the PostgreSQL deployment remains the durable,
multi-user deployment described in README.md.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[1]


def _app_data_root() -> Path:
    configured = os.environ.get("LMPC_DESKTOP_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "LMPC Compliance"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share") / \
        "lmpc-compliance"


def _configure_windows_dlls() -> None:
    """Make bundled Pango DLLs visible before WeasyPrint is imported."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    root = _bundle_root()
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(root)
    add_directory = getattr(os, "add_dll_directory", None)
    if add_directory:
        add_directory(str(root))


def _configure_environment() -> Path:
    root = _bundle_root()
    data_root = _app_data_root()
    data_root.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "LMPC_RULEPACK_PATH": str(root / "rulepack" / "current.json"),
        "LMPC_STORAGE_ROOT": str(data_root / "objects"),
        "LMPC_DB_URL": "",
        "LMPC_AUTH_MODE": "disabled",
        "LMPC_S3_BUCKET": "",
        "LMPC_S3_ENDPOINT": "",
        "LMPC_COOKIE_SECURE": "false",
    })
    _configure_windows_dlls()
    return data_root


def _port_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
        return True
    except OSError:
        return False


def _open_when_ready(url: str, host: str, port: int) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.15)


def _self_test() -> int:
    """Exercise the native-heavy code paths from inside the frozen bundle."""
    data_root = _configure_environment()
    from PIL import Image, ImageDraw, ImageFont
    from docx import Document
    from weasyprint import HTML

    from lmpc.engine.ocr import read_bytes
    from lmpc.server.main import app

    image = Image.new("RGB", (720, 240), "white")
    drawing = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    drawing.text((30, 85), "MRP Rs. 45.00", fill="black", font=font)
    raw = io.BytesIO()
    image.save(raw, format="PNG")
    tokens = read_bytes(raw.getvalue(), max_edge=720)

    pdf = HTML(string="<h1>LMPC portable self-test</h1><p>Report rendering works.</p>").write_pdf()
    doc = Document()
    doc.add_heading("LMPC portable self-test", 0)
    word = io.BytesIO()
    doc.save(word)
    pack = app.state.pipeline.rulepack
    result = {
        "status": "ok",
        "rulepack_version": pack["version"],
        "rulepack_sha256": pack["sha256"],
        "ocr_runtime": "ok",
        "ocr_tokens_detected": len(tokens),
        "pdf_runtime": "ok" if pdf.startswith(b"%PDF-") else "failed",
        "docx_runtime": "ok" if word.getvalue().startswith(b"PK") else "failed",
        "storage_root": str(data_root / "objects"),
    }
    if result["pdf_runtime"] != "ok" or result["docx_runtime"] != "ok":
        raise RuntimeError("portable report self-test failed")
    print(json.dumps(result, indent=2))
    return 0


def _serve(host: str, port: int, open_browser: bool) -> int:
    data_root = _configure_environment()
    if not _port_available(host, port):
        print(f"LMPC Compliance cannot start: {host}:{port} is already in use.",
              file=sys.stderr)
        return 2

    from lmpc.server.main import app
    import uvicorn

    url = f"http://{host}:{port}/"
    print("LMPC Compliance portable mode")
    print(f"Open: {url}")
    print(f"Local files: {data_root}")
    print("This window is the local server. Press Ctrl+C to stop it.")
    if open_browser:
        threading.Thread(
            target=_open_when_ready, args=(url, host, port), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LMPC Compliance on this computer")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=8000,
                        help="local HTTP port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the app in the default browser")
    parser.add_argument("--self-test", action="store_true",
                        help="test bundled OCR and report runtimes, then exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        print("--port must be between 1 and 65535", file=sys.stderr)
        return 2
    if args.self_test:
        return _self_test()
    return _serve(args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
