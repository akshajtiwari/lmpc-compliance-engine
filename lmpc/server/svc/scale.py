"""Client-reported scale references -> engine px_per_mm and panel dimensions.

An ISO ID-1 card is 85.60 mm x 53.98 mm (ISO/IEC 7810 ID-1). When the officer
captures the package with such a card lying flat on the same surface, the phone
sends the card's corner marks (and optionally the principal display panel's) in
image pixel coordinates. This module converts those marks into the absolute-scale
inputs the geometry checks consume, or returns None with a recorded reason so the
engine abstains instead of guessing. Every number here is deterministic: no scan
ever reads a model, only pinned card dimensions and coordinate geometry.

px_per_mm is the area-averaged scale over the marked panel plane: a single scalar
cannot represent an anisotropic (tilted) view exactly, so the homogeneity guard
bounds how far the local scale may vary before the measurement is refused. The
panel's own physical size, mapped back through the card's homography, is exact
for a coplanar rectangular face and is what the panel-area rule consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

ID1_LONG_MM = 85.60
ID1_SHORT_MM = 53.98
ID1_ASPECT = ID1_LONG_MM / ID1_SHORT_MM
# A detected scale reference outside this span is a mis-marked frame, not a
# plausible photograph: 0.05 px/mm is a 20 mm card in a 400 px frame, 50 px/mm is
# a sub-millimetre mark in the same frame.
PX_PER_MM_RANGE = (0.05, 50.0)
# A card quad whose pixel aspect strays this far from 1.586 is not the card the
# officer thinks it is; the bound still admits a ~34-degree viewing tilt.
ASPECT_TOLERANCE = 0.22
# Local px/mm across the measured quad's edges must agree within this ratio for
# the perspective correction to be trusted.
HOMOGENEITY_LIMIT = 1.35
# A panel coplanar with the card maps back to a true rectangle; a marked quad
# whose back-mapped corners shear this far off rectangular is a mis-mark.
RECTANGLE_COS_LIMIT = 0.2
RECTANGLE_EDGE_RATIO_LIMIT = 1.2
# Plausible principal-display-panel area under Rule 7(4): 1 cm2 .. 2500 cm2.
PANEL_AREA_CM2_RANGE = (1.0, 2500.0)
# The marked panel must not be absurdly small or large relative to the card.
PANEL_AREA_RATIO_RANGE = (0.5, 400.0)


@dataclass
class Measurements:
    px_per_mm: float
    pdp_w_cm: float | None = None
    pdp_h_cm: float | None = None
    notes: list[str] = field(default_factory=list)

    def as_meta(self) -> dict[str, float]:
        out = {"px_per_mm": round(self.px_per_mm, 4)}
        if self.pdp_w_cm is not None:
            out["pdp_w_cm"] = round(self.pdp_w_cm, 3)
        if self.pdp_h_cm is not None:
            out["pdp_h_cm"] = round(self.pdp_h_cm, 3)
        return out


def engine_measurements(mode: str, meta: dict[str, Any]) -> Measurements | None:
    """Turn stored scale-reference metadata into engine inputs, or None.

    Listing mode never receives absolute scale: Rule 6(10) has no geometry to
    measure and synthetic listing tokens would corrupt every millimetre check.
    """
    if mode != "PHYSICAL_PACKAGE":
        return None
    data = meta.get("scale_reference_data")
    if not isinstance(data, dict) or meta.get("scale_reference_type") != "ISO_ID1_CARD":
        return None
    quad = _quad(data.get("quad"))
    if quad is not None:
        return _from_card_quad(quad, _quad(data.get("panel_quad")))
    observed = data.get("observed_px")
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) \
            or observed <= 0:
        return None
    px_per_mm = observed / ID1_LONG_MM
    if not _in_range(px_per_mm, PX_PER_MM_RANGE):
        return None
    return Measurements(px_per_mm=px_per_mm,
                        notes=["scale from a marked card long edge; no corner data"])


def _from_card_quad(card, panel) -> Measurements | None:
    """Homography path: card corners in px (+ panel corners) -> scale and size."""
    if not _convex(card):
        return None
    corners_mm = _card_corners_mm()
    try:
        mm_to_px = _homography(corners_mm, card)
        inverse = np.linalg.inv(mm_to_px)
    except (np.linalg.LinAlgError, ValueError):
        return None
    if not _plausible_card(card, mm_to_px):
        return None
    scale_at_card = float(np.sqrt(abs(np.linalg.det(mm_to_px[:2, :2]))))
    if not _in_range(scale_at_card, PX_PER_MM_RANGE):
        return None
    measurement = Measurements(px_per_mm=scale_at_card,
                               notes=["scale from card corner marks"])
    if panel is None:
        return measurement
    return _with_panel(measurement, panel, inverse)


def _with_panel(current: Measurements, panel, inverse) -> Measurements | None:
    """Measure px_per_mm over the panel's own plane and derive its physical size."""
    if not _convex(panel):
        return None
    mapped = _map(panel, inverse)
    if mapped is None:
        return None
    area_px = _area(panel)
    area_mm = _area(mapped)
    if area_px <= 0 or area_mm <= 0:
        return None
    if not _in_range(area_px / area_mm / (current.px_per_mm ** 2),
                     PANEL_AREA_RATIO_RANGE):
        return None
    px_per_mm = float(np.sqrt(area_px / area_mm))
    if not _in_range(px_per_mm, PX_PER_MM_RANGE):
        return None
    if max(_edge_scales(panel, mapped)) / min(_edge_scales(panel, mapped)) \
            > HOMOGENEITY_LIMIT:
        return None
    if not _near_rectangle(mapped):
        return None
    if not _in_range(area_mm / 100.0, PANEL_AREA_CM2_RANGE):
        return None
    width_mm = float(np.linalg.norm(np.subtract(mapped[1], mapped[0])))
    height_mm = float(np.linalg.norm(np.subtract(mapped[3], mapped[0])))
    if width_mm <= 0 or height_mm <= 0 or not 0.2 <= height_mm / width_mm <= 5.0:
        return None
    current.px_per_mm = px_per_mm
    current.pdp_w_cm = width_mm / 10.0
    current.pdp_h_cm = height_mm / 10.0
    current.notes = ["scale and panel size from card and panel corner marks"]
    return current


def _plausible_card(card, mm_to_px) -> bool:
    """The quad must actually look like the pinned card, not another object."""
    mapped = _map(card, np.linalg.inv(mm_to_px))
    if mapped is None:
        return False
    long_px = (np.linalg.norm(np.subtract(card[1], card[0]))
               + np.linalg.norm(np.subtract(card[2], card[3]))) / 2
    short_px = (np.linalg.norm(np.subtract(card[2], card[1]))
                + np.linalg.norm(np.subtract(card[3], card[0]))) / 2
    if min(long_px, short_px) <= 0:
        return False
    aspect_error = abs((long_px / short_px) - ID1_ASPECT) / ID1_ASPECT
    return aspect_error <= ASPECT_TOLERANCE


def _edge_scales(panel, mapped) -> list[float]:
    """px/mm along each marked panel edge; disagreement means a tilted plane."""
    scales = []
    for index in range(4):
        nxt = (index + 1) % 4
        mm_span = float(np.linalg.norm(np.subtract(mapped[nxt], mapped[index])))
        px_span = float(np.linalg.norm(np.subtract(panel[nxt], panel[index])))
        if mm_span <= 0:
            continue
        scales.append(px_span / mm_span)
    return scales or [0.0]


def _near_rectangle(mapped) -> bool:
    """The back-mapped panel must be rectangular: the display face is.

    A genuinely coplanar rectangular panel projects to a quad whose corners map
    back through the card's homography onto a true rectangle. Sheared corners
    mean sloppy marks or a plane that is not parallel to the card's.
    """
    edges = [np.subtract(mapped[(index + 1) % 4], mapped[index]) for index in range(4)]
    lengths = [float(np.linalg.norm(edge)) for edge in edges]
    if min(lengths) <= 0:
        return False
    for first, second in ((0, 1), (1, 2)):
        cos_angle = abs(float(np.dot(edges[first], edges[second]))
                        / (lengths[first] * lengths[second]))
        if cos_angle > RECTANGLE_COS_LIMIT:
            return False
    for pair in ((0, 2), (1, 3)):
        if max(lengths[pair[0]], lengths[pair[1]]) / min(lengths[pair[0]],
                                                         lengths[pair[1]]) \
                > RECTANGLE_EDGE_RATIO_LIMIT:
            return False
    return True


def _card_corners_mm() -> list[tuple[float, float]]:
    # The phone marks corners clockwise starting at the first corner of the card's
    # long edge, so the destination rectangle is the card in landscape orientation.
    return [(0.0, 0.0), (ID1_LONG_MM, 0.0), (ID1_LONG_MM, ID1_SHORT_MM),
            (0.0, ID1_SHORT_MM)]


def _homography(src: list[tuple[float, float]],
                dst: list[tuple[float, float]]):
    """Exact 3x3 planar homography from four point pairs (h33 pinned to 1)."""
    rows = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    system = np.array(rows, dtype=float)
    _, _, vt = np.linalg.svd(system)
    solution = vt[-1]
    if abs(solution[-1]) < 1e-12:
        raise ValueError("degenerate homography")
    return (solution / solution[-1]).reshape(3, 3)


def _map(points, transform) -> list[tuple[float, float]] | None:
    try:
        projected = np.array([[x, y, 1.0] for x, y in points], dtype=float)
        moved = projected @ transform.T
        if np.any(np.abs(moved[:, 2]) < 1e-12):
            return None
        moved = moved[:, :2] / moved[:, 2:3]
    except (ValueError, FloatingPointError):
        return None
    if not np.all(np.isfinite(moved)):
        return None
    return [(float(x), float(y)) for x, y in moved]


def _cross2(a, b) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _area(points) -> float:
    return abs(_cross2(np.subtract(points[1], points[0]),
                       np.subtract(points[2], points[0]))) / 2 + abs(_cross2(
        np.subtract(points[2], points[0]),
        np.subtract(points[3], points[0]))) / 2


def _convex(quad) -> bool:
    signs = []
    for index in range(4):
        a, b, c = (np.array(quad[(index + offset) % 4], dtype=float)
                   for offset in range(3))
        cross = _cross2(b - a, c - b)
        if abs(cross) < 1e-9:
            return False
        signs.append(cross > 0)
    return len(set(signs)) == 1


def _quad(value) -> list[tuple[float, float]] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    out = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return None
        x, y = point
        if isinstance(x, bool) or isinstance(y, bool) \
                or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        out.append((float(x), float(y)))
    return out


def _in_range(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]
