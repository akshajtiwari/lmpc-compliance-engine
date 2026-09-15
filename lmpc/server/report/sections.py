"""A report as a list of sections, built once and rendered twice.

The PDF and the DOCX used to be two hand-parallel functions over the same snapshot, which
meant they could silently drift: a column added to one was simply missing from the other.
Both now consume this model, so a change lands in both documents or neither.

Nothing here reads the database or the object store — it is a pure function of the
snapshot, which is what keeps `content_sha256` meaningful.
"""
from __future__ import annotations

from typing import Any

#: Sections are one of: {"kind": "kv"|"table"|"list"|"text"|"images", ...}
Section = dict[str, Any]

OUTCOME_WORDS = {
    "PASS": "Meets the requirement",
    "FAIL": "Does not meet the requirement",
    "INDETERMINATE": "Could not be determined",
    "NOT_APPLICABLE": "Does not apply",
    "REVIEW_REQUIRED": "Needs a reviewer",
    "SYSTEM_ERROR": "The check could not run",
}

OVERALL_WORDS = {
    "COMPLIANT": "No violation found",
    "NON_COMPLIANT": "Violation found",
    "INCOMPLETE_EVIDENCE": "Not enough evidence to decide",
    "OUT_OF_SCOPE": "These rules do not apply",
    "REVIEW_REQUIRED": "A reviewing officer must decide",
    "SYSTEM_ERROR": "A check could not run",
}


#: A measurement is a physical quantity with a unit. Everything else in an evidence dict
#: — score, margin, best_candidate, the winning token's text — is how the engine reached
#: its conclusion, not what it measured, and putting it in a column headed "what we
#: measured" tells a manufacturer nothing they can act on.
UNITS = ("_mm", "_cm", "_cm2", "_cm3", "_px", "_ratio", "_g", "_ml", "_pt")
REQUIREMENT_MARKERS = ("required", "minimum", "min_", "_min", "maximum", "max_",
                       "_max", "threshold", "permitted", "allowed")


def _is_measurement(key: str) -> bool:
    """True for a physical quantity, including one expressed as a limit (`ratio_min`)."""
    stem = key
    for marker in ("_min", "_max"):
        if stem.endswith(marker):
            stem = stem[: -len(marker)]
    return (stem.endswith(UNITS) or stem in {"px_per_mm", "ratio", "area", "count"}
            or key.endswith(UNITS))


def _is_requirement(key: str) -> bool:
    return any(marker in key for marker in REQUIREMENT_MARKERS)


def measured_required(evidence: dict | None) -> tuple[str, str]:
    """Split a check's evidence into what was measured and what the law requires.

    The old report dumped `json.dumps(evidence)` into a single cell, which is the least
    readable thing in the document: an officer handing a report to a manufacturer should
    not have to parse JSON to see that a 1.4 mm digit needed to be 1.7 mm. Most checks are
    presence checks and measure nothing — those honestly say so rather than filling the
    column with scoring internals.
    """
    if not evidence:
        return "—", "—"
    measured: list[str] = []
    required: list[str] = []
    for key, value in sorted(evidence.items()):
        if value is None or isinstance(value, (dict, list)) or not _is_measurement(key):
            continue
        text = f"{_label(key)}: {_number(value)}"
        (required if _is_requirement(key) else measured).append(text)
    return ("; ".join(measured) or "—", "; ".join(required) or "—")


def _label(key: str) -> str:
    for marker in ("required_", "minimum_", "min_", "maximum_", "max_", "threshold_"):
        if key.startswith(marker):
            key = key[len(marker):]
    return key.replace("_", " ")


def _number(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def scan_sections(snapshot: dict, *, version: int, kind: str,
                  content_hash: str) -> list[Section]:
    """Every section of a single-scan report, in order."""
    evaluations = snapshot["evaluations"]
    applicable = [item for item in evaluations if item["outcome"] != "NOT_APPLICABLE"]
    skipped = len(evaluations) - len(applicable)
    counts: dict[str, int] = {}
    for item in evaluations:
        counts[item["outcome"]] = counts.get(item["outcome"], 0) + 1

    identity = snapshot["identification"]
    investigation = snapshot.get("investigation") or {}
    declared = {item["field"]: item.get("text") for item in snapshot["declarations"]
                if item.get("text")}

    sections: list[Section] = [
        {"kind": "cover",
         "title": "Legal Metrology compliance report",
         "verdict": snapshot["overall"],
         "verdict_word": OVERALL_WORDS.get(snapshot["overall"], snapshot["overall"] or ""),
         "kind_label": ("Field copy — not legally finalised" if kind == "FIELD"
                        else "Finalised report"),
         "rows": _cover_rows(identity, investigation, declared, snapshot, version)},
        {"kind": "counts", "title": "What the checks found", "counts": counts,
         "words": OUTCOME_WORDS,
         "note": (f"{skipped} further check{'s' if skipped != 1 else ''} did not apply to "
                  "this package; they are listed below." if skipped else "")},
        {"kind": "table", "title": "Findings",
         "columns": ["Rule", "What it requires", "What we measured", "What is required",
                     "Verdict", "Authority"],
         "rows": [_finding_row(item) for item in applicable]},
        {"kind": "notapplicable", "title": "Checks that did not apply",
         "items": [" · ".join(part for part in (item["check"], item.get("clause"))
                              if part)
                   for item in evaluations if item["outcome"] == "NOT_APPLICABLE"]},
        {"kind": "images", "title": "Evidence photographed",
         "images": snapshot["images"],
         "note": ("Every required panel was photographed through the guided camera."
                  if snapshot["coverage"]["asserted"] else
                  "Not every panel was captured through the guided camera, so this report "
                  "cannot state that a declaration is absent — only that it was not found.")},
    ]
    if snapshot.get("notes"):
        sections.append({"kind": "notes", "title": "Officer notes",
                         "notes": snapshot["notes"]})
    if snapshot.get("trail"):
        sections.append({"kind": "table", "title": "What happened to this inspection",
                         "columns": ["When", "Action", "By", "Detail"],
                         "rows": snapshot["trail"]})
    if snapshot["disclosures"]:
        sections.append({"kind": "list", "title": "Known gaps in the compiled law",
                         "items": snapshot["disclosures"]})
    if kind == "FINALIZED":
        sections.append({"kind": "signoff", "title": "Reviewing officer"})
    sections.append({"kind": "integrity", "title": "Integrity and provenance",
                     "rows": [
                         ("Rulepack version", snapshot["rulepack"]["version"]),
                         ("Law current to", snapshot["rulepack"].get("current_to")),
                         ("Rulepack SHA-256", snapshot["rulepack"]["sha256"]),
                         ("Report content SHA-256", content_hash)]})
    return sections


def _cover_rows(identity: dict, investigation: dict, declared: dict,
                snapshot: dict, version: int) -> list[tuple[str, Any]]:
    rows = [("Product", declared.get("manufacturer_block")
             or investigation.get("subject_brand") or "Not identified on the label"),
            ("Declared quantity", declared.get("net_quantity") or "—"),
            ("Declared price", declared.get("mrp") or "—"),
            ("Commodity category", identity.get("category")),
            ("Inspection type", "Online listing" if identity.get("mode") ==
             "ECOMMERCE_LISTING" else "Physical package"),
            ("Captured on", snapshot.get("captured_at"))]
    if investigation:
        rows.insert(0, ("Investigation", investigation.get("name")))
        if investigation.get("location_text"):
            rows.insert(1, ("Place", investigation["location_text"]))
    rows += [("Inspection reference", identity.get("scan_id")),
             ("Report version", version)]
    return [(label, value) for label, value in rows if value not in (None, "")]


def _finding_row(item: dict) -> list[str]:
    """The clause is the legal reference an officer quotes, so it stays in the document
    even when a fuller gazette citation is also available."""
    measured, required = measured_required(item.get("evidence"))
    rule = " · ".join(part for part in (item["check"], item.get("clause")) if part)
    return [rule, item["reason"], measured, required,
            OUTCOME_WORDS.get(item["outcome"], item["outcome"]),
            citation(item.get("citation") or {}) or item.get("clause", "")]


def citation(value: dict) -> str:
    return " · ".join(str(value[key]) for key in ("gsr", "dated", "page")
                      if value.get(key))
