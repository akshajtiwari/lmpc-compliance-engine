"""The pinned OpenAPI snapshot must match the live schema (plan §8 item 7)."""
import json
from pathlib import Path

from lmpc.server.main import create_app
from lmpc.server.openapi_dump import SNAPSHOT, schema


def test_openapi_snapshot_is_current():
    assert SNAPSHOT.exists(), (
        "docs/api/openapi.json is missing — run python -m lmpc.server.openapi_dump")
    live = json.dumps(schema(), sort_keys=True)
    pinned = json.dumps(json.loads(SNAPSHOT.read_text()), sort_keys=True)
    assert live == pinned, (
        "docs/api/openapi.json is stale — run python -m lmpc.server.openapi_dump "
        "and review the contract diff before committing")