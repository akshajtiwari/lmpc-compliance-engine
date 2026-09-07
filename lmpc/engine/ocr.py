"""
Real OCR. RapidOCR runs the PP-OCR detection and recognition models under ONNX Runtime —
the same model family as PaddleOCR, without the heavy dependency.

One honest caveat runs through everything below: a detection box is not a glyph. The box
around "MRP Rs. 45.00" spans ascenders and descenders and includes padding, so its height
OVERSTATES the letter height that Rule 7(2) measures. Absolute millimetre verdicts must
therefore not be taken from box height alone — which, with no scale reference in these
photographs either, is why the font check abstains on real images.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from .model import Token

CAP_RATIO = 0.62      # rough cap-height fraction of a text-line box; a bias, not a fact


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def read(path: str | Path, panel: str = "FRONT",
         min_conf: float = 0.0) -> list[Token]:
    """Recognise one image into Tokens carrying real geometry and real confidence."""
    result, _ = _engine()(str(path))
    toks: list[Token] = []
    for box, text, score in (result or []):
        score = float(score)          # RapidOCR returns confidence as a string
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y = int(min(xs)), int(min(ys))
        w, h = int(max(xs) - x), int(max(ys) - y)
        if not text.strip() or score < min_conf:
            continue
        toks.append(Token(text=text.strip(), x=x, y=y, w=w, h=h,
                          conf=float(score), panel=panel,
                          cap_height_px=h * CAP_RATIO))
    return toks


def read_product(rec: dict, min_conf: float = 0.0) -> tuple[list[Token], set[str]]:
    """Read every photographed panel of one product."""
    toks, panels = [], set()
    for p in rec["panels"]:
        toks += read(p["path"], panel=p["panel"], min_conf=min_conf)
        panels.add(p["panel"])
    return toks, panels
