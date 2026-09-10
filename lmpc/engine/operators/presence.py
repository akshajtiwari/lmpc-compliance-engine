"""Operator 1 — presence. Is the declaration there at all?"""
from __future__ import annotations
from ..model import Verdict, Scan, Field
from ._common import r


def presence(spec, scan: Scan, fields: dict[str, Field | None]):
    f = fields.get(spec["field"])
    if f:
        return r(spec, Verdict.PASS, f"found on {f.panel} panel",
                 text=f.text, score=f.score, margin=f.margin, panel=f.panel)
    # Absence of evidence is not evidence of absence. Three separate reasons we might
    # not have found a declaration, and only one of them is a violation.
    if not scan.coverage_asserted:
        return r(spec, Verdict.INDETERMINATE,
                 "not found, and the capture was not confirmed to cover every surface; "
                 "absence cannot be concluded",
                 panels_captured=sorted(scan.panels_captured))
    if not {"FRONT", "BACK"} <= scan.panels_captured:
        missing = sorted({"FRONT", "BACK"} - scan.panels_captured)
        return r(spec, Verdict.INDETERMINATE,
                 f"not found, but {', '.join(missing)} panel(s) were never photographed",
                 panels_captured=sorted(scan.panels_captured))

    d = getattr(fields, "diag", {}).get(spec["field"], {})
    from ..extract import NEAR_MISS, LEGIBLE
    if d.get("top", 0) >= NEAR_MISS:
        return r(spec, Verdict.INDETERMINATE,
                 "something resembling this declaration is present but could not be "
                 "identified with enough confidence to judge it",
                 best_candidate=d.get("best_text"), score=d.get("top"),
                 margin=d.get("margin"))

    illegible = [t for t in scan.tokens if t.conf < LEGIBLE]
    if illegible:
        return r(spec, Verdict.INDETERMINATE,
                 f"{len(illegible)} of {len(scan.tokens)} text regions were read below "
                 f"the legibility threshold; absence cannot be concluded from an "
                 f"unreadable image",
                 min_confidence=round(min(t.conf for t in illegible), 2))

    return r(spec, Verdict.FAIL, "declaration not found on any legibly photographed panel",
             panels_captured=sorted(scan.panels_captured))