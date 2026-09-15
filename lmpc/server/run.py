"""Safe local server launcher with an explicit mobile/LAN mode."""
from __future__ import annotations

import argparse
import os

import uvicorn

from .config import Settings
from .net import lan_address


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LMPC local server")
    parser.add_argument("--lan", action="store_true",
                        help="listen on the private LAN for the mobile app")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = Settings.from_env()
    host = "127.0.0.1"
    if args.lan:
        if settings.auth_mode == "disabled":
            raise SystemExit("LAN mode refuses to run with LMPC_AUTH_MODE=disabled")
        address = lan_address()
        if not address:
            raise SystemExit("No private LAN address was found; connect Wi-Fi and retry")
        host = "0.0.0.0"
        advertised = settings.public_base_url or f"http://{address}:{args.port}"
        os.environ["LMPC_PUBLIC_BASE_URL"] = advertised
        print(f"LMPC Field server: {advertised}", flush=True)
        print(f"Pair a phone at {advertised}/pair", flush=True)
    uvicorn.run(
        "lmpc.server.main:app", host=host, port=args.port, reload=args.reload,
        reload_dirs=["lmpc"] if args.reload else None)


if __name__ == "__main__":
    main()
