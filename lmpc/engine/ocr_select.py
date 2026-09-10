"""Per-region recognition selection (M.19, Part 8.1).

Two specialist recognisers read the same detected regions: the bundled English model
and the fetched Devanagari one. Neither is general — the English model cannot emit one
Devanagari character, the Devanagari one is slightly worse on English. So the English
reading is the default and the specialist takes a region only when its reading actually
carries the script.

`[ESTIMATE]` until measured against a labelled Hindi set (Part 25.5).
"""
from __future__ import annotations

from .model import Token
from .ocr_models import DEVANAGARI, paths, verify

DEV_RANGE = range(0x0900, 0x0980)          # Devanagari block

_recogniser = None                          # built once, or None when not fetched


def _dev_fraction(text: str) -> float:
    glyphs = [c for c in text if not c.isspace()]
    if not glyphs:
        return 0.0
    return sum(1 for c in glyphs if ord(c) in DEV_RANGE) / len(glyphs)


def available() -> bool:
    return verify()


def _recogniser_for_crops():
    """The Devanagari recogniser over raw crops; None until the model is fetched."""
    global _recogniser
    if _recogniser is None:
        if not available():
            return None
        from rapidocr_onnxruntime.ch_ppocr_rec.text_recognize import TextRecognizer
        model, keys = paths()
        _recogniser = TextRecognizer({
            "model_path": str(model), "rec_keys_path": str(keys),
            "rec_batch_num": 6, "rec_img_shape": DEVANAGARI["img_shape"],
        })
    return _recogniser


def pick(en: tuple[str, float] | None, dev: tuple[str, float] | None
         ) -> tuple[str, float] | None:
    """The English reading is the default; the specialist wins what it can represent.

    Asymmetric on purpose. The Devanagari model is slightly worse on English, so its
    authority extends only to readings that actually carry Devanagari — the bundled
    model cannot emit a single Devanagari character, so on a Hindi crop its reading is
    not a competing opinion, it is noise. Between two same-script readings the English
    model keeps the region (Part 8.1).
    """
    if en is None:
        return dev
    if dev is None:
        return en
    if _dev_fraction(dev[0]) > 0.5 and _dev_fraction(en[0]) < 0.2:
        return dev
    return en


def rewrite(img, tokens: list[Token]) -> None:
    """Re-read each token's region with the specialist and rewrite the tokens in place.

    `img` is the prepared frame. Tokens keep their geometry and provenance — only the
    reading changes.
    """
    rec = _recogniser_for_crops()
    if rec is None or not tokens:
        return
    crops = [img[max(0, t.y):t.y + t.h, max(0, t.x):t.x + t.w] for t in tokens]
    readings, _ = rec(crops)
    for t, dev in zip(tokens, readings):
        winner = pick((t.text, t.conf), (dev[0], float(dev[1])))
        if winner is not None:
            t.text, t.conf = winner