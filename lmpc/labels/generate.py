"""
Synthetic label images with exact ground truth.

Real photographs give you no ground truth: nobody knows to a tenth of a millimetre how
tall the MRP glyphs are. Here we choose the panel size in centimetres, choose the cap
height in millimetres, render at a known DPI, then measure what was actually drawn. The
expected verdict is therefore derivable rather than asserted.

OCR is simulated, not skipped: token geometry comes from the renderer (exact), and
`noise` degrades the text the way a real recogniser does — O/0, l/1, S/5 confusions,
dropped separators, split ordinals, and reduced confidence.
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lmpc.engine.model import Token, Scan

DPI = 300
PX_PER_MM = DPI / 25.4
FONT_PATHS = ["/usr/share/fonts/TTF/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"]

CONFUSIONS = {"0": "O", "1": "l", "5": "S", "8": "B", "O": "0", "I": "1"}


def _font_file() -> str:
    for p in FONT_PATHS:
        if Path(p).exists():
            return p
    raise RuntimeError("no usable TTF font found")


def font_for_cap_height(mm: float) -> tuple[ImageFont.FreeTypeFont, float]:
    """Pick the pixel em-size whose CAP height is closest to `mm`, and report what was
    actually achieved. Rule 7 measures the letter, not the em box."""
    target_px = mm * PX_PER_MM
    path, best = _font_file(), None
    for size in range(4, 400):
        f = ImageFont.truetype(path, size)
        box = f.getbbox("H")                       # (x0, y0, x1, y1)
        cap = box[3] - box[1]
        if best is None or abs(cap - target_px) < abs(best[1] - target_px):
            best = (f, cap, size)
        if cap > target_px * 1.6:
            break
    f, cap, _ = best
    return f, cap


def noisy(text: str, level: float, rng: random.Random) -> tuple[str, float]:
    """Degrade text the way a recogniser does. Returns (text, confidence)."""
    if level <= 0:
        return text, 1.0
    out = []
    for ch in text:
        if ch in CONFUSIONS and rng.random() < level:
            out.append(CONFUSIONS[ch])
        elif ch == " " and rng.random() < level * 0.3:
            continue                                # dropped space: "2022were published"
        elif ch.isalnum() and rng.random() < level * 0.08:
            out.append(rng.choice("abcdefghijklmnopqrstuvwxyz"))
        else:
            out.append(ch)
    return "".join(out), max(0.35, 1.0 - level * 1.4)


@dataclass
class Label:
    scan: Scan
    image: Path | None
    truth: dict


def make(*, lines: list[tuple[str, str]], pdp_h_cm: float, pdp_w_cm: float,
         cap_mm: float = 3.0, noise: float = 0.0, panels=("FRONT", "BACK"),
         seed: int = 0, write_to: Path | None = None, crowd_quantity: bool = False,
         **scan_kw) -> Label:
    """`lines` is [(panel, text), ...]. Everything else describes the physical package."""
    rng = random.Random(seed)
    font, cap_px = font_for_cap_height(cap_mm)
    w_px, h_px = int(pdp_w_cm * 10 * PX_PER_MM), int(pdp_h_cm * 10 * PX_PER_MM)
    img = Image.new("RGB", (max(w_px, 200), max(h_px, 200)), "white")
    draw = ImageDraw.Draw(img)

    tokens, y = [], int(6 * PX_PER_MM)
    for panel, text in lines:
        shown, conf = noisy(text, noise, rng)
        box = draw.textbbox((0, 0), shown, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        x = int(5 * PX_PER_MM)
        if panel == "FRONT":
            draw.text((x, y), shown, font=font, fill="black")
        tokens.append(Token(text=shown, x=x, y=y, w=tw, h=th, conf=conf,
                            panel=panel, cap_height_px=cap_px))
        y += th + int((0.6 if crowd_quantity else 4.0) * PX_PER_MM)

    path = None
    if write_to:
        write_to.parent.mkdir(parents=True, exist_ok=True)
        img.save(write_to, dpi=(DPI, DPI))
        path = write_to

    # A rendered label is fully known: we drew every panel and every glyph, so coverage
    # and glyph geometry are facts here. Neither is true of a photograph.
    scan = Scan(tokens=[t for t in tokens if t.panel in panels],
                panels_captured=set(panels), pdp_h_cm=pdp_h_cm, pdp_w_cm=pdp_w_cm,
                px_per_mm=PX_PER_MM, coverage_asserted=True, glyph_segmentation=True,
                **scan_kw)
    return Label(scan=scan, image=path,
                 truth={"cap_mm_requested": cap_mm,
                        "cap_mm_rendered": round(cap_px / PX_PER_MM, 3),
                        "pdp_area_cm2": round(pdp_h_cm * pdp_w_cm, 2),
                        "dpi": DPI, "noise": noise})


COMPLIANT_LINES = [
    ("FRONT", "CRISPY DELIGHT BISCUITS"),
    ("FRONT", "MRP Rs. 45.00 (incl. of all taxes)"),
    ("FRONT", "Net Qty: 500 g"),
    ("FRONT", "MFG 02/2025"),
    ("BACK",  "Consumer Care: care@foofoods.in, 1800-123-456"),
    ("BACK",  "Manufactured by Foo Foods Pvt Ltd, Pune 411001"),
]
