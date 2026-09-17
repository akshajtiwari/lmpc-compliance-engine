"""Safe local server launcher with an explicit mobile/LAN mode."""
from __future__ import annotations

import argparse
import os

import uvicorn

from .config import Settings
from .net import lan_address
from .tls import ensure_certificate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LMPC local server")
    parser.add_argument("--lan", action="store_true",
                        help="listen on the private LAN for the mobile app")
    parser.add_argument("--tls", action="store_true",
                        help="serve HTTPS with a self-signed certificate the phone pins "
                             "(the preview APK cannot pin yet; see docs/evidence/DEVICE-DRILL.md)")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = Settings.from_env()
    host = "127.0.0.1"
    scheme = "http"
    tls_args: dict = {}
    if args.lan:
        if settings.auth_mode == "disabled":
            raise SystemExit("LAN mode refuses to run with LMPC_AUTH_MODE=disabled")
        address = lan_address()
        if not address:
            raise SystemExit("No private LAN address was found; connect Wi-Fi and retry")
        host = "0.0.0.0"
        if args.tls:
            from pathlib import Path
            material = ensure_certificate(
                Path(settings.storage_root).resolve().parent / "tls",
                addresses=[address])
            os.environ["LMPC_TLS_CERT"] = material["cert"]
            os.environ["LMPC_TLS_KEY"] = material["key"]
            tls_args = {"ssl_certfile": material["cert"], "ssl_keyfile": material["key"]}
            scheme = "https"
        advertised = settings.public_base_url or f"{scheme}://{address}:{args.port}"
        os.environ["LMPC_PUBLIC_BASE_URL"] = advertised
        print(f"LMPC Field server: {advertised}", flush=True)
        print(f"Pair a phone at {advertised}/pair", flush=True)
    uvicorn.run(
        "lmpc.server.main:app", host=host, port=args.port, reload=args.reload,
        reload_dirs=["lmpc"] if args.reload else None, **tls_args)


if __name__ == "__main__":
    main()