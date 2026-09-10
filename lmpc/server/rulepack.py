"""The rulepack the service will judge every scan against, verified at start-up.

No scan ever reads a PDF: the compiled rulepack is the only law the request path sees.
If its content hash does not verify, the service refuses to become ready — a silently
edited rulepack would forge the legal basis of every finding it produces."""
from __future__ import annotations
import json
import threading

from lmpc.lawc.build import BuildFailed, digest, verify

_lock = threading.Lock()
_pack: dict | None = None


def load(path: str) -> dict:
    """Read and verify once; re-verified on every restart, never on every request."""
    global _pack
    with open(path) as fh:
        pack = json.load(fh)
    try:
        verify(pack)
    except BuildFailed as e:
        raise RuntimeError(f"E_RULEPACK_INTEGRITY: {e}") from e
    with _lock:
        _pack = pack
    return pack


def get() -> dict:
    if _pack is None:
        raise RuntimeError("rulepack not loaded — start-up refused or not run")
    return _pack


def intact(pack: dict | None = None) -> bool:
    p = pack or _pack
    return p is not None and digest(p) == p.get("sha256")


def summary() -> dict:
    """The identity every verdict cites."""
    p = get()
    return {"version": p["version"], "rulepack_sha256": p["sha256"],
            "current_to": p["currency"]["newest_instrument"]}