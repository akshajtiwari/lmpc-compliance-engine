"""The Part 13 schema: every spec table exists with the guarantees the spec names.
Metadata-level — dialect exercises belong to the compose integration run (Part 21)."""
import pytest
from sqlalchemy import UniqueConstraint

from lmpc.server.db.models import Base, Product, RuleEvaluation, Scan, ScanImage


def _table(name):
    return Base.metadata.tables[name]


def test_every_part13_table_exists():
    assert set(Base.metadata.tables) == {
        "jurisdictions", "users", "refresh_tokens", "commodity_categories",
        "manufacturers", "products", "scans", "scan_images", "extracted_declarations",
        "rule_evaluations", "compliance_reports", "rulepacks", "amendment_ledger",
        "audit_log"}


def test_scan_idempotency_is_a_database_guarantee():
    assert _table("scans").columns["client_uuid"].unique is True


def test_jurisdiction_scope_uses_ltree_and_gist():
    path = _table("jurisdictions").columns["path"]
    index = next(item for item in _table("jurisdictions").indexes
                 if item.name == "idx_jurisdiction_path")
    assert str(path.type) == "LTREE"
    assert index.dialect_options["postgresql"]["using"] == "gist"


def test_email_is_case_insensitive_and_mfa_secret_is_modelled():
    users = _table("users")
    assert str(users.columns["email"].type) == "CITEXT"
    assert users.columns["email"].unique is True
    assert "mfa_secret_enc" in users.columns


def test_product_dedup_is_a_stored_generated_column():
    col = _table("products").columns["dedup_key"]
    assert col.computed is not None and col.computed.persisted is True
    assert col.unique is not None


def test_rule_evaluations_append_only():
    checks = {c.name: str(getattr(c, "sqltext", "")) for c in
              _table("rule_evaluations").constraints if getattr(c, "name", None)}
    assert "ck_eval_outcome" in checks
    assert "is_override" in checks["ck_override_provenance"]


def test_one_active_rulepack_is_a_partial_unique_index():
    idx = next(i for i in _table("rulepacks").indexes
               if i.name == "one_active_rulepack")
    assert idx.unique and "ACTIVE" in str(idx.dialect_options["postgresql"]["where"])


def test_scans_captured_at_drives_the_law_not_the_clock():
    assert _table("scans").columns["captured_at"].nullable is False   # P7


def test_report_versions_are_unique_per_scan():
    uq = next(u for u in _table("compliance_reports").constraints
              if isinstance(u, UniqueConstraint))
    assert [c.name for c in uq.columns] == ["scan_id", "version"]


@pytest.mark.parametrize("table,col", [
    ("scans", "coverage_asserted"), ("scans", "captured_at"),
    ("rule_evaluations", "reason"), ("rule_evaluations", "citation"),
])
def test_mandatory_columns_reject_nulls(table, col):
    assert _table(table).columns[col].nullable is False
