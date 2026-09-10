"""Specialist recogniser models (M.19, Part 25.5).

The recogniser RapidOCR ships is the Chinese PP-OCRv4 model: its 6,625-character set
contains zero Devanagari characters, so Hindi extraction was impossible, not merely
untested. This module fetches a Devanagari specialist into `models/`, pinned by content
hash — a model that changed behind our back would quietly change every Hindi finding.
The English recogniser stays bundled with RapidOCR; only the specialist is fetched.
"""
from __future__ import annotations
import hashlib
import json
import urllib.request
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "models"
MANIFEST = DIR / "manifest.json"

# PP-OCRv3-style mobile recogniser trained on Hindi, with its per-line CTC dictionary.
# Height is 32 (older input shape), unlike the bundled v4 model's 48.
DEVANAGARI = {
    "base": "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/hindi/",
    "model": "rec.onnx",
    "keys": "dict.txt",
    "img_shape": [3, 32, 320],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry() -> dict:
    """The recorded hashes; empty when the specialist has never been fetched."""
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def paths() -> tuple[Path, Path]:
    return DIR / DEVANAGARI["model"], DIR / DEVANAGARI["keys"]


def verify() -> bool:
    """True when the files exist and still match the recorded hashes."""
    model, keys = paths()
    hashes = entry().get("devanagari", {})
    if not (model.exists() and keys.exists() and hashes):
        return False
    return (_sha256(model) == hashes.get("model")
            and _sha256(keys) == hashes.get("keys"))


def fetch() -> dict:
    """Download the specialist, record its content hash, refuse to overwrite a pin."""
    DIR.mkdir(parents=True, exist_ok=True)
    model, keys = paths()
    recorded = entry().get("devanagari", {})
    for name, path in ((DEVANAGARI["model"], model), (DEVANAGARI["keys"], keys)):
        if path.exists() and recorded:
            if _sha256(path) != recorded.get(name, ""):
                raise RuntimeError(f"{path} does not match the pinned hash — not replaced")
            continue
        url = DEVANAGARI["base"] + name
        with urllib.request.urlopen(url, timeout=120) as r:
            path.write_bytes(r.read())
    manifest = entry()
    manifest["devanagari"] = {"rec.onnx": _sha256(model), "dict.txt": _sha256(keys)}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    m = fetch()
    print("devanagari recogniser pinned:",
          ", ".join(f"{k[:12]} {v[:16]}" for k, v in m["devanagari"].items()))