"""The capture client stays installable, offline-capable and free of legal logic."""
from __future__ import annotations

from pathlib import Path

WEB = Path("lmpc/server/web")


def test_pwa_shell_is_small_and_has_no_network_dependency():
    assets = [WEB / name for name in ("index.html", "app.css", "app.js", "sw.js")]
    assert sum(path.stat().st_size for path in assets) < 250_000
    content = "\n".join(path.read_text() for path in assets)
    assert 'src="https://' not in content
    assert 'href="https://' not in content
    assert "url(\"https://" not in content


def test_offline_queue_uses_the_required_indexeddb_stores():
    script = (WEB / "app.js").read_text()
    assert all(f'createObjectStore("{name}"' in script
               for name in ("scans", "images", "outbox"))
    assert 'crypto.subtle.digest("SHA-256"' in script
    assert "coverageFor(value)" in script


def test_client_quality_gates_match_the_capture_spec():
    script = (WEB / "app.js").read_text()
    assert "quality.long_edge >= 1200" in script
    assert "quality.blur >= 100" in script
    assert "quality.luma >= 40 && quality.luma <= 215" in script
    assert "quality.glare <= .03" in script


def test_client_contains_no_rule_ids_or_legal_thresholds():
    script = (WEB / "app.js").read_text()
    assert "LMPC-R" not in script
    assert "min_mm" not in script
    assert "rulepack/current" not in script
