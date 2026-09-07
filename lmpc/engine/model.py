"""Data model. Everything the rule engine sees traces back to pixels or to the rulepack."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"        # evidence or law insufficient — not a violation
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass
class Token:
    """One OCR result: text plus where it sat, in pixels."""
    text: str
    x: int; y: int; w: int; h: int
    conf: float = 1.0
    panel: str = "FRONT"
    cap_height_px: float | None = None
    # Which raw OCR regions this token was built from. Assembled candidates share
    # provenance with their parts, which is how the margin test avoids comparing a line
    # against a rephrasing of itself.
    src: frozenset = frozenset()
    # True when this candidate's text was repaired (respaced or joined). Repairs help
    # LOCATE a declaration; they must never be used to READ its value.
    repaired: bool = False      # glyph height excluding ascenders/descenders

    @property
    def cx(self) -> float: return self.x + self.w / 2
    @property
    def cy(self) -> float: return self.y + self.h / 2


@dataclass
class Scan:
    tokens: list[Token]
    # The date the package was inspected. Every verdict is judged by the law in force on
    # this day - never by today's law. Without it, an amendment would silently rewrite
    # findings made years earlier.
    captured_at: str = "2026-09-07"
    panels_captured: set[str] = field(default_factory=lambda: {"FRONT"})
    mode: str = "PHYSICAL_PACKAGE"
    category: str = "GENERIC"
    buyer_type: str = "RETAIL"
    is_imported: bool = False
    is_molded: bool = False
    other_law_requires_same_info: bool = False
    package_shape: str = "RECTANGULAR"
    # Scale reference. None => absolute-millimetre checks abstain rather than guess.
    px_per_mm: float | None = None
    pdp_h_cm: float | None = None
    pdp_w_cm: float | None = None
    net_quantity_g: float | None = None
    net_quantity_ml: float | None = None
    capacity_cm3: float | None = None
    is_outer_package: bool = False
    # True only when the capture flow confirmed every surface was photographed. A photo
    # library labels an image "ingredients" because it shows the ingredients - that is not
    # the same as having seen the whole back panel. Without an assertion of coverage,
    # "we did not find the MRP" can never become "the MRP is missing".
    coverage_asserted: bool = False
    # True only when glyph-level segmentation is available. A detection box spans
    # ascenders, descenders and padding, so its height is not a letter height.
    glyph_segmentation: bool = False
    outer_is_transparent: bool = False

    def pdp_area_cm2(self) -> float | None:
        """Rule 7(4). Rectangular: h x w of the PDP face. Cylindrical: 0.40 x h x
        circumference. Other: 0.40 x total surface. Top, bottom, can flanges and
        bottle shoulders/necks are excluded."""
        if self.pdp_h_cm is None or self.pdp_w_cm is None:
            return None
        if self.package_shape == "RECTANGULAR":
            return self.pdp_h_cm * self.pdp_w_cm
        return 0.40 * self.pdp_h_cm * self.pdp_w_cm


@dataclass
class Field:
    """A candidate declaration, always traceable to the tokens it came from."""
    kind: str
    text: str
    tokens: list[Token]
    score: float
    margin: float                            # gap to the runner-up candidate
    normalized: dict = field(default_factory=dict)

    @property
    def panel(self) -> str: return self.tokens[0].panel if self.tokens else "?"


@dataclass
class Result:
    check: str
    clause: str
    verdict: Verdict
    reason: str
    citation: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
