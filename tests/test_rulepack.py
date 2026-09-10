"""The rulepack is the thing every verdict is compared against. If it is wrong or stale,
nothing downstream can be right. These tests guard that."""
import copy
import pytest
from lmpc.lawc import build as B


@pytest.fixture(scope="module")
def pack():
    return B.load()


def test_current_to_the_newest_2026_instrument(pack):
    assert pack["currency"]["newest_instrument"] == "G.S.R. 418(E)"   # 29 May 2026
    assert pack["currency"]["chain_links_verified"] >= 12


def test_every_chain_gap_is_disclosed_with_a_named_reviewer(pack):
    for gap in pack["currency"]["acknowledged_gaps"]:
        assert gap["reviewer"] and gap["reviewed_on"] and gap["text"]


def test_table_I_matches_the_2017_gazette(pack):
    """The values that were repealed in 2017 must not reappear, and the current ones
    must be exactly what G.S.R. 629(E) page 11 prints."""
    check = next(c for c in pack["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")
    rows = check["params"]["rows"]
    assert [(r["upper_cm2"], r["min_mm"], r["molded_mm"]) for r in rows] == [
        (50, 1.0, 1.5), (100, 1.5, 3.0), (500, 2.5, 4.0),
        (2500, 4.0, 6.0), (None, 6.0, 6.0)]
    assert check["params"]["source_instrument"] == "G.S.R. 629(E)"
    assert check["params"]["input"] == "pdp_area_cm2"      # NOT net quantity (repealed)


def test_table_I_boundaries_are_flagged_unconfirmed(pack):
    """pdftotext drops the '≤' glyph. Until a reviewer rules, no row may claim its
    boundary operator was confirmed."""
    check = next(c for c in pack["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")
    assert all(not r["boundary_confirmed_by_human"] for r in check["params"]["rows"])
    assert check["verdict_ceiling"] == "INDETERMINATE_NEAR_BOUNDARY"


def test_build_refuses_when_the_gazette_disagrees_with_the_reviewer():
    """Silent drift is the failure we cannot accept: if an amendment changes a value a
    human approved, the build must stop, not ship."""
    extracted = {"rows": [{"band": "A < 50", "min_height_mm": 9.9,
                           "min_height_molded_mm": 1.5, "boundary_operators": ["<"],
                           "needs_human_confirmation": True}]}
    with pytest.raises(B.BuildFailed, match="re-review"):
        B.check_table_against_review(extracted, [{"upper_cm2": 50, "min_mm": 1.0,
                                                  "molded_mm": 1.5}], "lmpc/r7/table-I")


def test_build_refuses_on_a_row_count_change():
    with pytest.raises(B.BuildFailed, match="rows"):
        B.check_table_against_review({"rows": []}, [{"upper_cm2": 50, "min_mm": 1.0,
                                                     "molded_mm": 1.5}], "n")


def test_rulepack_is_hash_addressed(pack):
    assert len(pack["sha256"]) == 64 and pack["sha256"][:8] in pack["version"]


def test_ecommerce_mode_excludes_only_the_packing_date(pack):
    """Rule 6(10): every mandatory declaration EXCEPT month and year of packing."""
    ex = set(pack["modes"]["ECOMMERCE_LISTING"]["excludes"])
    assert "LMPC-R6-1-D-MFG-DATE" in ex
    assert "LMPC-R6-1-E-MRP" not in ex


CHECK_KEYS = {"check", "node", "clause", "operator", "field", "effective_from",
              "effective_to", "citation", "verdict_ceiling", "ceiling_reason",
              "only_when", "not_required_when", "boundary_review", "params",
              "table_effective_from", "superseded", "confirmed_values"}
GATE_KEYS = {"id", "clause", "node", "operator", "citation", "params", "effect",
             "exceptions"}
PARAM_KEYS = {"regex", "phrase_any", "phrase_present_at", "phrase_absent_below",
              "illustrations", "predicate", "tiers", "numerator", "denominator", "min",
              "exclude_glyphs", "field", "above_below_multiple", "left_right_multiple",
              "input", "compare", "molded_column_when", "rows", "versions",
              "source_instrument", "allowed_scripts", "additional_permitted",
              "on_two_values", "higher_second_value", "not_after", "not_before",
              "on_violation", "capacity_cm3_at_or_below", "relaxes", "expr",
              "tolerance_pct", "on_mismatch", "any_of", "when"}


def test_bindings_carry_no_key_the_engine_does_not_read(pack):
    """A key nothing reads is a lie in the config: a reader assumes it is enforced."""
    dead = []
    for c in pack["checks"]:
        dead += [f"{c['check']}.{k}" for k in c if k not in CHECK_KEYS]
        dead += [f"{c['check']}.params.{k}" for k in c.get("params", {})
                 if k not in PARAM_KEYS]
    for g in pack["gates"]:
        dead += [f"{g['id']}.{k}" for k in g if k not in GATE_KEYS]
    assert not dead, f"keys the engine never reads: {dead}"
