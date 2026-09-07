"""Operator behaviour, especially the distinction between 'not there' and 'not readable'."""
import pytest
from lmpc.lawc.build import load
from lmpc.engine.model import Token, Scan, Verdict
from lmpc.engine.engine import run
from lmpc.engine import extract as X
from lmpc.labels.generate import make, COMPLIANT_LINES


@pytest.fixture(scope="module")
def pack():
    return load()


def verdict(pack, scan, check):
    return {r.check: r.verdict for r in run(pack, scan)["results"]}[check]


def test_missing_panel_is_indeterminate_not_fail(pack):
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18, pdp_w_cm=12, cap_mm=3,
               panels=("FRONT",), net_quantity_g=500)
    assert verdict(pack, lab.scan, "LMPC-R6-1-F-CONSUMER-CARE") is Verdict.INDETERMINATE


def test_illegible_image_cannot_prove_absence(pack):
    scan = Scan(tokens=[Token("###### ???", 0, 0, 100, 20, conf=0.4)],
                panels_captured={"FRONT", "BACK"})
    assert verdict(pack, scan, "LMPC-R6-1-E-MRP") is Verdict.INDETERMINATE


def test_clean_empty_label_does_fail(pack):
    """A legible photograph of every panel showing no MRP is a genuine violation."""
    scan = Scan(tokens=[Token("HELLO WORLD", 0, 0, 100, 20, conf=1.0),
                        Token("SOME BRAND", 0, 40, 100, 20, conf=1.0, panel="BACK")],
                panels_captured={"FRONT", "BACK"})
    assert verdict(pack, scan, "LMPC-R6-1-E-MRP") is Verdict.FAIL


def test_exempt_package_is_never_evaluated(pack):
    scan = Scan(tokens=[Token("Sachet", 0, 0, 50, 10)], net_quantity_g=8)
    res = run(pack, scan)
    assert res["overall"] == "OUT_OF_SCOPE"
    assert all(r.verdict is Verdict.NOT_APPLICABLE for r in res["results"])
    assert "GATE-R26-EXEMPT" in res["gates_fired"]


def test_tobacco_is_carved_out_of_that_exemption(pack):
    scan = Scan(tokens=[Token("Sachet", 0, 0, 50, 10)], net_quantity_g=8,
                category="TOBACCO", panels_captured={"FRONT", "BACK"})
    assert "GATE-R26-EXEMPT" not in run(pack, scan)["gates_fired"]


def test_no_scale_reference_abstains_rather_than_guesses(pack):
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18, pdp_w_cm=12, cap_mm=1.0,
               net_quantity_g=500)
    lab.scan.px_per_mm = None
    assert verdict(pack, lab.scan, "LMPC-R7-2-MIN-HEIGHT") is Verdict.INDETERMINATE


def test_ambiguous_candidates_are_not_guessed():
    """Two blocks that look equally like the MRP must not be resolved by coin flip."""
    toks = [Token("MRP Rs. 45.00 (incl. of all taxes)", 0, 0, 300, 20),
            Token("MRP Rs. 52.00 (incl. of all taxes)", 0, 40, 300, 20)]
    assert X.extract(Scan(tokens=toks), ["mrp"])["mrp"] is None


def test_extraction_is_deterministic():
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18, pdp_w_cm=12, noise=0.2, seed=7)
    a = X.extract(lab.scan, ["mrp", "net_quantity"])
    b = X.extract(lab.scan, ["mrp", "net_quantity"])
    assert {k: (v.text if v else None) for k, v in a.items()} == \
           {k: (v.text if v else None) for k, v in b.items()}


def test_every_verdict_carries_a_citation(pack):
    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18, pdp_w_cm=12, cap_mm=3,
               net_quantity_g=500)
    for r in run(pack, lab.scan)["results"]:
        assert r.citation, f"{r.check} produced a verdict with no legal citation"
