"""
The documents must agree with each other, not only with the code.

`test_spec_consistency.py` checks the spec against the running system. It cannot catch the
failure that actually happened: a correction landed in the specification while four other
documents went on telling readers a GPU was required and two named an OCR configuration the
system does not have.

Documents are read by different people. The brief is read on day one, the plan in planning,
the spec while building. A claim corrected in one and left standing in another is worse
than never having corrected it, because now the project contradicts itself.

Canonical facts are derived from code and the rulepack wherever possible, so this file does
not become another thing to keep in sync by hand.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DOCS = Path("docs")
ROOT_README = Path("README.md")
PACK = Path("rulepack/current.json")

# Reports in docs/evidence/ are dated records. They are corrected by an appended note, not
# by editing the findings, so their body text is exempt from the claim checks below.
EVIDENCE = DOCS / "evidence"
ARCHIVE = DOCS / "archive"


def live_docs() -> list[Path]:
    """Current documents: everything except dated evidence and superseded archive."""
    return sorted(p for p in list(DOCS.glob("*.md")) + [ROOT_README]
                  if p.exists() and ARCHIVE not in p.parents and EVIDENCE not in p.parents)


def all_docs() -> list[Path]:
    return sorted(p for p in list(DOCS.rglob("*.md")) + [ROOT_README]
                  if p.exists() and ARCHIVE not in p.parents)


# --------------------------------------------------------------- retracted claims ---
# Each entry is a claim the project once made and has since disproved. Leaving one standing
# in any current document means a reader will act on it. The reason is carried here so a
# future engineer knows why the phrase is forbidden rather than deleting the rule.
RETRACTED = [
    (r"GPU is not optional",
     "M.18 — every 'GPU' timing was CPU; CPU meets the latency budget"),
    (r"needs? a GPU",
     "M.18 — a GPU is optional headroom, not a requirement"),
    (r"minutes on CPU",
     "M.18 — the cause was 64 MP frames, not the absence of a GPU"),
    (r"PaddleOCR",
     "we ship PP-OCR models under ONNX Runtime via RapidOCR, not the PaddlePaddle runtime"),
    (r"Devanagari (?:is )?(?:in the lexicon but )?never exercised",
     "M.19 — Hindi was impossible, not untested: the shipped recogniser has no Devanagari"),
]


@pytest.mark.parametrize("pattern,reason", RETRACTED)
def test_no_current_document_repeats_a_retracted_claim(pattern, reason):
    offenders = []
    for p in live_docs():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(pattern, line, re.I):
                # A line that explicitly retracts the claim is allowed to quote it.
                if re.search(r"previously|turned out|was wrong|no longer|retract|correction|"
                             r"M\.1[89]|M\.20|not a requirement|optional|instead of|"
                             r"rather than|forbidden|banned", line, re.I):
                    continue
                offenders.append(f"{p}:{i}: {line.strip()[:100]}")
    assert not offenders, f"retracted claim ({reason}) still present:\n" + "\n".join(offenders)


# ------------------------------------------------------------------ agreed numbers ---
def canonical_facts() -> dict[str, int]:
    pack = json.loads(PACK.read_text())
    from lmpc.engine.operators import OPERATORS
    spec = (DOCS / "02-BUILD-SPEC.md").read_text(encoding="utf-8")
    defects = len(set(re.findall(r"^\| M\.(\d+) \|", spec, re.M)))
    return {"checks": len(pack["checks"]), "gates": len(pack["gates"]),
            "operators": len(OPERATORS), "defects": defects}


def test_defect_count_agrees_across_documents():
    """The brief, the README and the spec each quote a defect total to a different reader."""
    n = canonical_facts()["defects"]
    wrong = []
    for p in live_docs():
        text = p.read_text(encoding="utf-8")
        # The pipe must be allowed: these totals live in table cells, which is exactly
        # where the stale "17" hid when the register had moved to 20.
        for m in re.finditer(r"(?:defects?|bugs?)[^.\n]{0,50}?\*\*(\d+)\*\*|"
                             r"\*\*(\d+)\*\*[^.\n]{0,40}?(?:defects?|bugs?)|"
                             r"\b(?:Seventeen|Eighteen|Nineteen|Twenty|Twenty-one)\b\s+(?:defects?|bugs?)",
                             text, re.I):
            WORDS = {"seventeen": 17, "eighteen": 18, "nineteen": 19,
                     "twenty": 20, "twenty-one": 21}
            if m.group(1) or m.group(2):
                got = int(m.group(1) or m.group(2))
            else:
                got = WORDS.get(m.group(0).split()[0].lower())
            if got and got != n and got > 5:    # ignore small incidental numbers
                wrong.append(f"{p}: says {got}, register holds {n}")
    assert not wrong, "defect totals disagree:\n" + "\n".join(wrong)


def test_check_and_gate_counts_agree_across_documents():
    f = canonical_facts()
    wrong = []
    for p in live_docs():
        text = p.read_text(encoding="utf-8")
        for label, key in (("checks", "checks"), ("gates", "gates")):
            for m in re.finditer(rf"(\d+)\s+{label}\b", text, re.I):
                got = int(m.group(1))
                # "24 campaign checks" and "24 validation checks" count something else.
                window = text[max(0, m.start() - 40):m.end() + 10].lower()
                if any(w in window for w in ("campaign", "validation", "consistency",
                                             "adversarial", "rbac", "acceptance")):
                    continue
                if got != f[key] and got > 2:
                    wrong.append(f"{p}: '{got} {label}' but the rulepack has {f[key]}")
    assert not wrong, "rule counts disagree:\n" + "\n".join(wrong)


# ------------------------------------------------------------------- navigability ---
def test_every_live_document_is_listed_in_the_index():
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    missing = [p.name for p in DOCS.glob("*.md")
               if p.name != "README.md" and p.name not in index]
    assert not missing, f"documents absent from docs/README.md: {missing}"


def test_every_evidence_report_is_listed_in_the_index():
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    missing = [p.name for p in EVIDENCE.glob("*.md") if p.name not in index]
    assert not missing, f"evidence reports absent from docs/README.md: {missing}"


def test_internal_document_links_resolve():
    broken = []
    for p in all_docs():
        for target in re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", p.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://")):
                continue
            if not (p.parent / target).resolve().exists():
                broken.append(f"{p} → {target}")
    assert not broken, "broken document links:\n" + "\n".join(broken)


# ------------------------------------------------ evidence reports carry corrections ---
def test_evidence_reports_whose_findings_were_superseded_carry_a_correction():
    """A dated record is corrected by appending, never by editing. But it MUST be
    appended — an uncorrected report is read as current fact."""
    for name in ("REAL-WORLD-TEST.md", "WIDE-REAL-WORLD-TEST.md", "VALIDATION-CAMPAIGN.md"):
        text = (EVIDENCE / name).read_text(encoding="utf-8")
        assert "Correction" in text, f"{name} states superseded findings with no correction"
        assert "M.18" in text and "M.19" in text, \
            f"{name}'s correction does not reference the defects that superseded it"


# --------------------------------------------------------------- spec self-coherence ---
def test_spec_version_header_matches_document_control():
    spec = (DOCS / "02-BUILD-SPEC.md").read_text(encoding="utf-8")
    header = re.search(r"\*\*Version:\*\*\s*([\d.]+)", spec)
    assert header, "the spec has no version in its header"
    rows = re.findall(r"^\|\s*([\d.]+)\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|", spec, re.M)
    assert rows, "the spec has no document-control history"
    assert header.group(1) == rows[-1], \
        f"header says v{header.group(1)}, document control ends at v{rows[-1]}"


def test_every_principle_is_referenced_where_it_is_enforced():
    """A principle nobody cites is decoration."""
    spec = (DOCS / "02-BUILD-SPEC.md").read_text(encoding="utf-8")
    # Principles appear as "**P1** | …" in the summary table and "**P1.** …" in prose.
    defined = set(re.findall(r"\*\*(P\d)\*\*", spec))
    assert len(defined) >= 9, f"expected at least 9 principles, found {sorted(defined)}"
    for p in sorted(defined):
        assert len(re.findall(rf"\b{p}\b", spec)) >= 2, \
            f"{p} is defined but never cited anywhere in the specification"
