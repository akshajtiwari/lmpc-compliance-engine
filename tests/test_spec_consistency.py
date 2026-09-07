"""
The specification must describe the system that exists.

Documentation drift is not cosmetic here: the spec is the build document, and a threshold
documented wrongly is a threshold someone will implement wrongly. The previous revision
described a `numeric_predicate` without its repair refusal — that is, a system that would
still pass an unrounded price.

Part 18.4 item 8 of the spec promises this check runs in CI. This is that check.
"""
import json
import re
from pathlib import Path

import pytest

from lmpc.engine import extract, lexicon, ocr
from lmpc.engine.operators import OPERATORS

SPEC = Path("docs/02-BUILD-SPEC.md")
PACK = Path("rulepack/current.json")

pytestmark = pytest.mark.skipif(
    not (SPEC.exists() and PACK.exists()),
    reason="run `python -m lmpc.lawc.build` to produce the rulepack")


@pytest.fixture(scope="module")
def spec() -> str:
    return SPEC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pack() -> dict:
    return json.loads(PACK.read_text())


def test_every_check_in_the_rulepack_is_documented(spec, pack):
    missing = sorted(c["check"] for c in pack["checks"] if c["check"] not in spec)
    assert not missing, f"checks absent from the build spec: {missing}"


def test_every_gate_in_the_rulepack_is_documented(spec, pack):
    missing = sorted(g["id"] for g in pack["gates"] if g["id"] not in spec)
    assert not missing, f"gates absent from the build spec: {missing}"


def test_every_operator_is_documented(spec):
    missing = sorted(o for o in OPERATORS if o not in spec)
    assert not missing, f"operators absent from the build spec: {missing}"


def test_no_binding_names_an_operator_that_does_not_exist(pack):
    named = {c["operator"] for c in pack["checks"]}
    assert not (named - set(OPERATORS)), \
        f"rulepack names unimplemented operators: {sorted(named - set(OPERATORS))}"


@pytest.mark.parametrize("name,value", [
    ("FLOOR", extract.FLOOR), ("MARGIN", extract.MARGIN),
    ("NEAR_MISS", extract.NEAR_MISS), ("LEGIBLE", extract.LEGIBLE),
    ("ACCUSE", extract.ACCUSE), ("MAX_EDGE", ocr.MAX_EDGE),
    ("CAP_RATIO", ocr.CAP_RATIO), ("THRESHOLD", lexicon.THRESHOLD),
])
def test_documented_thresholds_match_the_code(spec, name, value):
    """A threshold in the spec that the code does not use is a lie a reader will act on."""
    trimmed = str(value).rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
    assert str(value) in spec or trimmed in spec, \
        f"{name}={value} is not stated anywhere in the build spec"


def test_table_I_values_match_the_rulepack(spec, pack):
    chk = next(c for c in pack["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")
    for row in chk["params"]["rows"]:
        assert f"{row['min_mm']} mm" in spec, f"Table-I minimum {row['min_mm']} mm undocumented"
        assert f"{row['molded_mm']} mm" in spec, f"Table-I moulded {row['molded_mm']} mm undocumented"


def test_currency_claims_match_the_rulepack(spec, pack):
    c = pack["currency"]
    assert c["newest_instrument"] in spec, "the spec does not name the newest instrument"
    assert str(c["chain_links_verified"]) in spec, "chain link count undocumented"


def test_every_documented_defect_has_an_identifier(spec):
    """The register is cited from the principles table; every M.n must resolve."""
    cited = set(re.findall(r"\bM\.(\d+)\b", spec))
    defined = set(re.findall(r"^\| M\.(\d+) \|", spec, re.M))
    assert cited <= defined, f"defects cited but not defined: {sorted(cited - defined)}"


def test_no_language_model_in_the_runtime_dependency_tree():
    """P8. A dependency is the easiest way for one to arrive unnoticed."""
    banned = {"openai", "anthropic", "transformers", "llama_cpp",
              "langchain", "sentence_transformers", "google.generativeai"}
    reqs = Path("requirements.txt").read_text().lower()
    found = sorted(b for b in banned if b.split(".")[0] in reqs)
    assert not found, f"P8 violated — language-model packages declared: {found}"
