"""Plain-language rule guidance never changes the normative rulepack."""
from __future__ import annotations

from lmpc.lawc.build import load
from lmpc.server.svc.rule_help import decision_explanation, rule_detail
from lmpc.server.svc.scan_service import ScanRecord


def test_every_compiled_check_has_complete_review_guidance():
    pack = load()
    for check in pack["checks"]:
        detail = rule_detail(pack, check["check"])
        assert detail["title"] and detail["requirement"] and detail["method"]
        assert detail["evidence_needed"] and detail["authority"]
        assert set(detail["outcomes"]) == {
            "PASS", "FAIL", "INDETERMINATE", "NOT_APPLICABLE",
            "REVIEW_REQUIRED", "SYSTEM_ERROR",
        }


def test_industrial_out_of_scope_explanation_says_ocr_was_skipped():
    record = ScanRecord(
        client_uuid="10000000-0000-4000-8000-000000000001",
        captured_at="2026-09-10", mode="PHYSICAL_PACKAGE", category="FOOD",
        coverage_asserted=False, panels=[], images=[],
        overall="OUT_OF_SCOPE", metadata={"buyer_type": "INDUSTRIAL"},
    )

    explanation = decision_explanation(record)

    assert explanation["processing_stage"] == "Applicability gate"
    assert explanation["ocr_ran"] is False
    assert "Industrial" in explanation["summary"]
    assert "select Retail" in explanation["next_step"]
