"""Who may see which record.

Extracted from `AuthManager` so the access rules sit together and can be read in one
screen. Every one of them ultimately asks the same question — is this record inside the
principal's jurisdiction subtree — which `db/paths.py` answers identically on PostgreSQL
and SQLite.
"""
from __future__ import annotations

from ..api.errors import ApiError
from ..db.paths import jurisdiction_contains
from .auth_core import Principal


class ScopeRules:
    """Mixed into AuthManager, which supplies `disabled`, `sessions` and `audit_denial`."""

    def ensure_scan_scope(self, principal: Principal, scan) -> None:
        if self.disabled or principal.role == "ADMIN":
            return
        if principal.role == "FIELD_OFFICER":
            allowed = scan.officer_id == principal.id
        else:
            allowed = self._jurisdiction_contains(
                principal.jurisdiction_id, scan.jurisdiction_id)
        if not allowed:
            self.audit_denial(principal, "scan", scan.id)
            raise ApiError("E_FORBIDDEN", "the scan is outside your authorised scope")
    def ensure_jurisdiction_scope(self, principal: Principal,
                                  jurisdiction_id: str) -> None:
        if self.disabled or principal.role == "ADMIN":
            return
        allowed = (principal.jurisdiction_id == jurisdiction_id
                   if principal.role == "FIELD_OFFICER" else
                   self._jurisdiction_contains(principal.jurisdiction_id, jurisdiction_id))
        if not allowed:
            self.audit_denial(principal, "jurisdiction", jurisdiction_id)
            raise ApiError("E_FORBIDDEN", "the jurisdiction is outside your authorised scope")

    def jurisdiction_allows(self, principal: Principal, jurisdiction_id: str) -> bool:
        """The same rule as ensure_jurisdiction_scope, as a question rather than a guard.

        A caller deciding whether a record is visible must answer 404, not 403: telling
        someone "forbidden" confirms that another jurisdiction's investigation exists."""
        if self.disabled or principal.role == "ADMIN":
            return True
        if principal.role == "FIELD_OFFICER":
            return principal.jurisdiction_id == jurisdiction_id
        return self._jurisdiction_contains(principal.jurisdiction_id, jurisdiction_id)

    def _jurisdiction_contains(self, root: str | None, target: str | None) -> bool:
        """One containment rule, shared with the repository scoping in review_db. An
        access-control predicate that disagrees between two backends is a security
        bug, not a portability detail."""
        with self.sessions() as session:  # type: ignore[operator]
            return jurisdiction_contains(session, root, target)

