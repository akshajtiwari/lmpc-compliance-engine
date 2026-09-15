"""One report covering every scan in an investigation.

Not a concatenation of individual reports: a cover for the folder, the aggregate picture,
a one-line-per-product table an enforcement officer can read at a glance, and then the
findings for each product that failed. A folder of forty packets should not produce a
document nobody will open.
"""
from __future__ import annotations

from collections import Counter

from .sections import OUTCOME_WORDS, OVERALL_WORDS, citation

MAX_DETAIL = 25


def sections(folder: dict, scans: list[dict], *, version: int, kind: str,
             content_hash: str, disclosures: list[str], rulepack: dict) -> list[dict]:
    overall = Counter(scan["overall"] for scan in scans if scan.get("overall"))
    failing = [scan for scan in scans if scan.get("overall") == "NON_COMPLIANT"]
    violations = Counter()
    for scan in scans:
        for item in scan.get("evaluations", []):
            if item["outcome"] == "FAIL":
                violations[item["check"]] += 1

    model: list[dict] = [
        {"kind": "cover",
         "title": f"Investigation report — {folder.get('name')}",
         "verdict": "NON_COMPLIANT" if failing else "COMPLIANT",
         "verdict_word": (f"{len(failing)} of {len(scans)} products carry a violation"
                          if failing else f"No violation found across {len(scans)} products"),
         "kind_label": ("Field copy — not legally finalised" if kind == "FIELD"
                        else "Finalised report"),
         "rows": [(label, value) for label, value in (
             ("Investigation", folder.get("name")),
             ("Subject", folder.get("subject_brand")),
             ("Place", folder.get("location_text")),
             ("Type", (folder.get("investigation_type") or "").replace("_", " ").lower()),
             ("Opened", folder.get("opened_at")),
             ("Status", folder.get("status")),
             ("Products inspected", len(scans)),
             ("Report version", version)) if value not in (None, "")]},
        {"kind": "counts", "title": "Across the whole investigation",
         "counts": dict(overall), "words": OVERALL_WORDS,
         "note": (f"{len(scans) - sum(overall.values())} inspection(s) had not finished "
                  "processing when this report was produced."
                  if sum(overall.values()) < len(scans) else "")},
    ]
    if violations:
        model.append({"kind": "table", "title": "Most common violations",
                      "columns": ["Rule", "Products affected"],
                      "rows": [[check, count]
                               for check, count in violations.most_common(10)]})
    model.append({
        "kind": "table", "title": "Every product inspected",
        "columns": ["Captured", "Category", "Verdict", "Main finding"],
        "rows": [[scan.get("captured_at"), scan.get("category"),
                  OVERALL_WORDS.get(scan.get("overall"), scan.get("overall") or "pending"),
                  _headline(scan)] for scan in scans]})

    for scan in failing[:MAX_DETAIL]:
        model.append({
            "kind": "table",
            "title": f"{scan.get('captured_at')} · {scan.get('category')} — findings",
            "columns": ["Rule", "What it requires", "Verdict", "Authority"],
            "rows": [[" · ".join(p for p in (item["check"], item.get("clause")) if p),
                      item["reason"],
                      OUTCOME_WORDS.get(item["outcome"], item["outcome"]),
                      citation(item.get("citation") or {})]
                     for item in scan.get("evaluations", [])
                     if item["outcome"] not in ("NOT_APPLICABLE", "PASS")]})
    if len(failing) > MAX_DETAIL:
        model.append({"kind": "list", "title": "Further detail",
                      "items": [f"{len(failing) - MAX_DETAIL} more non-compliant products "
                                "are listed above; their full findings are in their "
                                "individual reports."]})
    if disclosures:
        model.append({"kind": "list", "title": "Known gaps in the compiled law",
                      "items": disclosures})
    if kind == "FINALIZED":
        model.append({"kind": "signoff", "title": "Reviewing officer"})
    model.append({"kind": "integrity", "title": "Integrity and provenance",
                  "rows": [("Rulepack version", rulepack.get("version")),
                           ("Law current to", rulepack.get("current_to")),
                           ("Rulepack SHA-256", rulepack.get("sha256")),
                           ("Report content SHA-256", content_hash)]})
    return model


def _headline(scan: dict) -> str:
    """The first failing check, which is what an officer scans the column for."""
    for item in scan.get("evaluations", []):
        if item["outcome"] == "FAIL":
            return item["reason"]
    return "—"
