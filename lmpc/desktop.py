"""Portable launcher used by the Windows release bundle.

The executable keeps a durable SQLite repository and immutable image/report objects below
the current user's application-data folder, so investigations survive a restart and the
build can pair with a phone — enrollments and sessions are database rows, so there is no
pairing without a real store.

It remains a single-user field package. The PostgreSQL deployment is still the durable,
multi-user deployment described in README.md.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .desktop_console import print_addresses, print_pairing_banner


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
    fontconfig_root = root / "etc" / "fonts"
    os.environ["FONTCONFIG_FILE"] = str(fontconfig_root / "fonts.conf")
    os.environ["FONTCONFIG_PATH"] = str(fontconfig_root)
    add_directory = getattr(os, "add_dll_directory", None)
    if add_directory:
        add_directory(str(root))


def _database_url(data_root: Path) -> str:
    return "sqlite+pysqlite:///" + str(data_root / "lmpc.sqlite3")


def _configure_environment() -> Path:
    """Export the LMPC_* settings this machine's copy runs under.

    Authentication is on. It used to be disabled, which was safe for a loopback-only demo
    but made the build unable to issue a Field-app enrollment at all: AccountService
    refuses to manage accounts without local authentication, and the LAN launcher refuses
    to bind a wider address when auth is off. Both refusals are correct; the fix is to
    satisfy them, not to weaken them.
    """
    root = _bundle_root()
    data_root = _app_data_root()
    data_root.mkdir(parents=True, exist_ok=True)
    db_url = _database_url(data_root)
    os.environ.update({
        "LMPC_RULEPACK_PATH": str(root / "rulepack" / "current.json"),
        "LMPC_STORAGE_ROOT": str(data_root / "objects"),
        "LMPC_S3_BUCKET": "",
        "LMPC_S3_ENDPOINT": "",
        "LMPC_COOKIE_SECURE": "false",
    })
    from lmpc.server.db import desktop_bootstrap
    record = desktop_bootstrap.run(data_root, db_url)
    os.environ.update(desktop_bootstrap.environment(data_root, record, db_url))
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


def _attach_pairing(app, data_root: Path, port: int, advertised: str, allow: bool,
                    scheme: str = "http"):
    """Give the running app the state behind /pair: identities, QR, and the LAN switch."""
    from lmpc.server.db.desktop_bootstrap import credentials_path
    from lmpc.server.svc.pairing import PairingService

    record = json.loads(credentials_path(data_root).read_text(encoding="utf-8"))
    app.state.pairing = PairingService(app.state.accounts, app.state.auth, record, port,
                                       advertised=advertised, network_open=allow,
                                       scheme=scheme)
    return app.state.pairing


def _serve(host: str, port: int, open_browser: bool, advertised: str = "",
           allow: bool = False, tls: bool = False) -> int:
    # A console is line-buffered; a redirected log is not, and the pairing banner is the
    # whole point of the output. Without this a headless server writes its QR and its
    # address to the log only when it exits.
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(line_buffering=True)
    data_root = _configure_environment()
    if not _port_available(host, port):
        print(f"LMPC Compliance cannot start: {host}:{port} is already in use.",
              file=sys.stderr)
        return 2

    scheme = "http"
    tls_args: dict = {}
    if tls:
        from lmpc.server.net import lan_candidates
        from lmpc.server.tls import ensure_certificate
        material = ensure_certificate(
            data_root / "tls", addresses=[c.host for c in lan_candidates()])
        os.environ["LMPC_TLS_CERT"] = material["cert"]
        os.environ["LMPC_TLS_KEY"] = material["key"]
        tls_args = {"ssl_certfile": material["cert"], "ssl_keyfile": material["key"]}
        scheme = "https"

    from lmpc.server.main import app
    import uvicorn

    pairing = _attach_pairing(app, data_root, port, advertised, allow, scheme)
    local = f"{scheme}://127.0.0.1:{port}/"
    pair_url = f"{local}pair"
    print("LMPC Compliance portable mode")
    print(f"Open: {local}")
    print(f"Connect a phone: {pair_url}")
    print(f"Local files: {data_root}")
    if scheme == "https":
        print("TLS is on: the QR carries the certificate pin the phone must hold. "
              "A preview APK without certificate pinning cannot connect to an "
              "HTTPS pairing yet.")
    print_pairing_banner(pairing, host)
    print("This window is the local server. Press Ctrl+C to stop it.")
    if open_browser:
        threading.Thread(
            target=_open_when_ready, args=(pair_url, "127.0.0.1", port),
            daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info", **tls_args)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LMPC Compliance on this computer")
    parser.add_argument("--loopback-only", action="store_true",
                        help="refuse phone connections entirely (no pairing)")
    parser.add_argument("--host", default=None,
                        help="bind address (default: all interfaces, gated until you "
                             "allow phone connections on the pairing page)")
    parser.add_argument("--port", type=int, default=8000,
                        help="local HTTP port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the app in the default browser")
    parser.add_argument("--self-test", action="store_true",
                        help="test bundled OCR and report runtimes, then exit")
    parser.add_argument("--allow-phones", action="store_true",
                        help="accept phone connections from the start, instead of "
                             "waiting for someone to allow them on the pairing page "
                             "(for a server nobody is sitting at)")
    parser.add_argument("--public-url", default="",
                        help="the address phones should dial, when it is not one of this "
                             "computer's own — a public host name or a tunnel, e.g. "
                             "https://lmpc.example.gov.in")
    parser.add_argument("--tls", action="store_true",
                        help="serve HTTPS with a self-signed certificate and put its pin "
                             "in the QR. A phone without certificate pinning cannot "
                             "connect to an HTTPS pairing yet, so this is opt-in.")
    parser.add_argument("--addresses", action="store_true",
                        help="list this computer's network addresses and say which a "
                             "phone could reach, then exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        print("--port must be between 1 and 65535", file=sys.stderr)
        return 2
    if args.addresses:
        return print_addresses()
    if args.self_test:
        return _self_test()
    if args.public_url:
        from lmpc.server.net import normalise_base_url
        try:
            args.public_url = normalise_base_url(args.public_url,
                                                 default_port=args.port)
        except ValueError as refused:
            print(f"--public-url: {refused}", file=sys.stderr)
            return 2
    # Bind every interface by default so pairing needs no restart, but answer nothing
    # from the network until the officer allows it on the pairing page.
    host = args.host or ("127.0.0.1" if args.loopback_only else "0.0.0.0")
    return _serve(host, args.port, not args.no_browser,
                  advertised=args.public_url, allow=args.allow_phones, tls=args.tls)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
