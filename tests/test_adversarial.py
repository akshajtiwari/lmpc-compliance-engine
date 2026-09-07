"""
Fail-tests. Every one of these asserts that the system REFUSES rather than guesses.

A compliance engine is judged by what it does when its inputs are wrong: a corrupt
gazette, an unreachable source, a tampered rulepack, a chain it cannot close. Producing a
confident answer in any of those states is the failure mode that matters.
"""
import json
import shutil
from pathlib import Path

import pytest

from lmpc.lawc import build as B, parse
from lmpc.engine.model import Token, Scan, Verdict
from lmpc.engine.engine import run, in_force
from lmpc.labels.generate import make, COMPLIANT_LINES

CORPUS = Path("corpus")
GENERAL = Path("corpus_general")


@pytest.fixture(scope="module")
def pack():
    return B.load()


# ------------------------------------------------------ ingestion under attack ---

def test_corrupt_pdf_does_not_crash_the_build(tmp_path):
    """A truncated or garbage file must be classified, not parsed as law."""
    shutil.copy(CORPUS / "2017-8xii.pdf", tmp_path / "good.pdf")
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4\n" + b"\x00" * 4000)
    (tmp_path / "empty.pdf").write_bytes(b"")
    try:
        out = parse.main(tmp_path)
    except Exception as e:                      # noqa: BLE001 - this is the assertion
        pytest.fail(f"corrupt input crashed ingestion: {type(e).__name__}: {e}")
    bad = [d for d in out["documents"] if d["file"] != "good.pdf"]
    assert all(d["self_gsr"] is None for d in bad), "law was invented from garbage"


def test_empty_corpus_fails_loudly(tmp_path):
    with pytest.raises(Exception):
        B.build(corpus=tmp_path, out=tmp_path / "rp")


def test_scanned_documents_are_excluded_not_guessed():
    """2011-2015 gazettes are two-column scans. They must be flagged for OCR, never
    half-parsed into a chain."""
    out = parse.main(CORPUS)
    scanned = [d for d in out["documents"] if d["kind"] != "DIGITAL"]
    assert scanned, "expected the pre-2016 scans in the corpus"
    assert all(d["self_gsr"] is None for d in scanned)


# ------------------------------------------------- identity and chain integrity ---

def test_gsr_numbers_collide_across_years_and_are_detected():
    """The bug that would have spliced a 2021 amendment onto a 2025 one."""
    out = parse.main(GENERAL)
    hits = {c["gsr"] for c in out["gsr_number_collisions"]}
    assert "G.S.R. 875(E)" in hits
    keys = next(c for c in out["gsr_number_collisions"]
                if c["gsr"] == "G.S.R. 875(E)")["instruments"]
    assert keys == ["G.S.R. 875(E)@2016", "G.S.R. 875(E)@2025"]


def test_chain_keys_include_the_year():
    out = parse.main(CORPUS)
    for w in out["chain"]["walk"]:
        assert "@" in w["key"] and w["key"].split("@")[1].isdigit()


def test_rule_families_are_walked_separately():
    """Merging families made the walk pick an arbitrary root and invent gaps."""
    out = parse.main(GENERAL)
    chains = out["chains_by_family"]
    assert len(chains) >= 2
    assert len(chains["G.S.R. 71(E)"]["walk"]) >= 12      # General Rules
    assert chains["G.S.R. 71(E)"] is not chains["G.S.R. 593(E)"]


def test_parser_generalises_to_an_unseen_rule_family():
    """Regexes were written against Packaged Commodities. They must not be overfit."""
    out = parse.main(GENERAL)
    d = out["documents"]
    identified = sum(1 for x in d if x["self_gsr"])
    lineage = sum(1 for x in d if x["prev_gsr"])
    assert identified / len(d) >= 0.9, f"only {identified}/{len(d)} self-identified"
    assert lineage / len(d) >= 0.9, f"only {lineage}/{len(d)} carried lineage"


# --------------------------------------------------------- the build must refuse ---

def test_build_refuses_an_unacknowledged_chain_hole(monkeypatch, tmp_path):
    real = parse.main

    def holed(d):
        out = real(d)
        out["chain"]["missing_documents"] = [
            {"gsr": "G.S.R. 999(E)", "dated": "1 January 2024",
             "referenced_by": "G.S.R. 418(E)"}]
        out["chain"]["complete"] = False
        return out

    monkeypatch.setattr(parse, "main", holed)
    with pytest.raises(B.BuildFailed, match="cannot be proven current"):
        B.build(out=tmp_path)


def test_build_refuses_a_disclosure_that_covers_a_bound_node(monkeypatch, tmp_path):
    """A gap may be disclosed only if it demonstrably touches nothing we check."""
    gaps = {"gaps": [{"gsr": "G.S.R. 910(E)", "dated": "2022-12-29",
                      "referenced_by": "G.S.R. 60(E)", "decision": "ACCEPT_WITH_DISCLOSURE",
                      "reviewer": "x", "reviewed_on": "2026-01-01",
                      "affects_nodes": ["lmpc/r7/table-I"], "disclosure": "d"}]}
    f = tmp_path / "gaps.yaml"
    f.write_text(json.dumps(gaps))
    monkeypatch.setattr(B, "GAPS", f)
    with pytest.raises(B.BuildFailed, match="cannot stand in for the document"):
        B.build(out=tmp_path)


def test_build_refuses_a_gap_with_no_named_reviewer(monkeypatch, tmp_path):
    gaps = {"gaps": [{"gsr": "G.S.R. 910(E)", "dated": "2022-12-29",
                      "referenced_by": "G.S.R. 60(E)", "decision": "ACCEPT_WITH_DISCLOSURE",
                      "reviewer": "", "reviewed_on": "", "disclosure": "d"}]}
    f = tmp_path / "gaps.yaml"
    f.write_text(json.dumps(gaps))
    monkeypatch.setattr(B, "GAPS", f)
    with pytest.raises(B.BuildFailed, match="named reviewer"):
        B.build(out=tmp_path)


# ------------------------------------------------- reproducibility and integrity ---

def test_same_corpus_produces_the_same_hash(tmp_path):
    a = B.build(out=tmp_path / "a")
    b = B.build(out=tmp_path / "b")
    assert a["sha256"] == b["sha256"]
    assert a["built_at"] != "" and "built_at" not in json.dumps(
        {k: v for k, v in a.items() if k == "sha256"})


def test_a_tampered_rulepack_is_rejected(tmp_path):
    B.build(out=tmp_path)
    p = tmp_path / "current.json"
    d = json.loads(p.read_text())
    d["checks"][0]["params"] = {"regex": ".*"}        # neuter a check
    p.write_text(json.dumps(d))
    with pytest.raises(B.BuildFailed, match="integrity check failed"):
        B.load(tmp_path)


def test_tampering_with_a_threshold_is_rejected(tmp_path):
    B.build(out=tmp_path)
    p = tmp_path / "current.json"
    d = json.loads(p.read_text())
    chk = next(c for c in d["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")
    chk["params"]["rows"][2]["min_mm"] = 0.1          # make everything compliant
    p.write_text(json.dumps(d))
    with pytest.raises(B.BuildFailed):
        B.load(tmp_path)


# ------------------------------------------------------------ temporal soundness ---

def test_a_rule_is_not_applied_before_it_existed(pack):
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
               net_quantity_g=500)
    lab.scan.captured_at = "2015-06-01"
    v = {r.check: r.verdict for r in run(pack, lab.scan)["results"]}
    assert v["LMPC-R6-1-E-MRP-FORM"] is Verdict.NOT_APPLICABLE     # prescribed 2017
    assert v["LMPC-R6-1-LL-UNIT-SALE-PRICE"] is Verdict.NOT_APPLICABLE  # 2022


def test_the_repealed_table_still_governs_an_old_inspection(pack):
    """2.2 mm on a 500 g pack: lawful under the pre-2018 table, unlawful under the
    current one. The same package must get different answers on different dates."""
    def verdict(day):
        lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.2,
                   net_quantity_g=500)
        lab.scan.captured_at = day
        return {r.check: r for r in run(pack, lab.scan)["results"]}["LMPC-R7-2-MIN-HEIGHT"]

    before, after = verdict("2017-12-31"), verdict("2018-01-01")
    assert before.verdict is Verdict.PASS and "net quantity" in before.reason
    assert after.verdict is Verdict.FAIL and "cm2 panel" in after.reason


def test_todays_amendment_cannot_rewrite_yesterdays_finding(pack):
    """Re-running an old scan against the current rulepack must reproduce the old law."""
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.2,
               net_quantity_g=500)
    lab.scan.captured_at = "2016-01-01"
    r = {x.check: x for x in run(pack, lab.scan)["results"]}["LMPC-R7-2-MIN-HEIGHT"]
    assert r.evidence["law_version"] == "2011-04-01"


def test_in_force_window_is_closed_at_both_ends():
    spec = {"effective_from": "2018-01-01", "effective_to": "2021-12-31"}
    assert not in_force(spec, "2017-12-31")
    assert in_force(spec, "2018-01-01")
    assert in_force(spec, "2021-12-31")
    assert not in_force(spec, "2022-01-01")


# ------------------------------------------------------ the engine must not guess ---

def test_a_verdict_never_lacks_its_legal_basis(pack):
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
               net_quantity_g=500)
    for r in run(pack, lab.scan)["results"]:
        assert r.citation, f"{r.check}: verdict with no citation"
        assert r.reason, f"{r.check}: verdict with no reason"


def test_a_broken_operator_reports_system_error_not_a_violation(pack):
    """An engineering bug must never surface as a legal finding against a trader."""
    bad = json.loads(json.dumps(pack))
    bad["checks"] = [dict(bad["checks"][0], operator="does_not_exist")]
    scan = Scan(tokens=[Token("x", 0, 0, 10, 10)], panels_captured={"FRONT", "BACK"})
    assert run(bad, scan)["results"][0].verdict is Verdict.SYSTEM_ERROR


def test_every_table_band_is_exercised(pack):
    """All five Table-I bands, not just the one the demo happens to use."""
    chk = next(c for c in pack["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")
    rows = chk["params"]["rows"]
    areas = [30, 75, 215, 1200, 4000]
    seen = set()
    for area, row in zip(areas, rows):
        side = (area ** 0.5)
        lab = make(lines=COMPLIANT_LINES, pdp_h_cm=side, pdp_w_cm=side,
                   cap_mm=row["min_mm"] + 1.0, net_quantity_g=500)
        r = {x.check: x for x in run(pack, lab.scan)["results"]}["LMPC-R7-2-MIN-HEIGHT"]
        assert r.verdict is Verdict.PASS, (area, r.reason)
        seen.add(r.evidence["required_mm"])
    assert seen == {r["min_mm"] for r in rows}, f"bands exercised: {seen}"


@pytest.mark.parametrize("area", [50, 100, 500, 2500])
def test_every_table_boundary_abstains(pack, area):
    """The '<' vs '≤' reading is unresolved at all four interior boundaries."""
    side = area ** 0.5
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=side, pdp_w_cm=side, cap_mm=3.0,
               net_quantity_g=500)
    r = {x.check: x for x in run(pack, lab.scan)["results"]}["LMPC-R7-2-MIN-HEIGHT"]
    assert r.verdict is Verdict.INDETERMINATE, f"{area} cm2 produced {r.verdict}"
