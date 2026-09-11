"""Emit the pinned OpenAPI snapshot (plan §8 item 7).

Run ``python -m lmpc.server.openapi_dump`` after any API change and commit the
result. ``tests/test_openapi_snapshot.py`` fails when the live schema drifts from
the committed snapshot, so a mobile/web contract change is always a reviewed diff.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def schema() -> dict:
    from .main import create_app

    return create_app().openapi()


def render(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero when the snapshot is stale")
    args = parser.parse_args()
    current = render(schema())
    if args.check:
        pinned = SNAPSHOT.read_text() if SNAPSHOT.exists() else ""
        if pinned != current:
            raise SystemExit(
                "docs/api/openapi.json is stale — run "
                "python -m lmpc.server.openapi_dump and commit the diff")
        print("openapi snapshot is current")
        return
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(current)
    print(f"wrote {SNAPSHOT}")


if __name__ == "__main__":
    main()