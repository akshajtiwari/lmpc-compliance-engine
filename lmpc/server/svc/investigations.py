"""Investigations over either the local database or the in-memory store.

The memory path exists for the same reason `ReviewService` has one: the engine and
contract tests build an app with no `LMPC_DB_URL`, and the folder API has to answer there
too. It is a dictionary with the same semantics, not a second implementation of the rules.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..api.errors import ApiError
from ..db.investigations import STATUSES, TYPES
from .investigation_db import InvestigationDb

SORTS = {"recent", "oldest", "name"}
MAX_NAME = 200


class InvestigationService:
    def __init__(self, scan_store, auth):
        self.scans = scan_store
        self.auth = auth
        self.db = InvestigationDb(scan_store) if hasattr(scan_store, "sessions") else None
        self._memory: dict[str, dict] = {}
        self._notes: dict[str, list[dict]] = {}
        self._by_client: dict[str, str] = {}

    # ---- writes ----------------------------------------------------------------

    def create(self, principal, values: dict) -> tuple[dict, bool]:
        payload = validate(values)
        payload["jurisdiction_id"] = (values.get("jurisdiction_id")
                                      or principal.jurisdiction_id)
        if not payload["jurisdiction_id"]:
            raise ApiError("E_VALIDATION",
                           "an investigation needs a jurisdiction; this account has none")
        self.auth.ensure_jurisdiction_scope(principal, payload["jurisdiction_id"])
        if self.db:
            return self.db.create(principal, payload)
        return self._memory_create(principal, payload)

    def update(self, principal, investigation_id: str, values: dict) -> dict:
        self._authorize(principal, investigation_id)
        changes = validate(values, partial=True)
        if self.db:
            return self.db.update(investigation_id, changes)
        row = self._memory_get(investigation_id)
        row.update({k: v for k, v in changes.items() if v is not None})
        row["updated_at"] = datetime.now(UTC).isoformat()
        if changes.get("status") == "CLOSED":
            row["closed_at"] = row["updated_at"]
        elif changes.get("status") == "OPEN":
            row["closed_at"] = None
        return row

    def add_note(self, principal, investigation_id: str, body: str,
                 storage_key: str | None = None, sha256: str | None = None) -> dict:
        self._authorize(principal, investigation_id)
        if not (body or "").strip():
            raise ApiError("E_VALIDATION", "a note needs a body")
        if self.db:
            return self.db.add_note(investigation_id, principal, body.strip(),
                                    storage_key, sha256)
        note = {"id": str(uuid.uuid4()), "body": body.strip(),
                "author": principal.full_name, "author_id": principal.id,
                "storage_key": storage_key, "sha256": sha256,
                "created_at": datetime.now(UTC).isoformat()}
        self._notes.setdefault(investigation_id, []).insert(0, note)
        return note

    # ---- reads -----------------------------------------------------------------

    def get(self, principal, investigation_id: str) -> dict:
        return self._authorize(principal, investigation_id)

    def notes(self, principal, investigation_id: str) -> list[dict]:
        self._authorize(principal, investigation_id)
        if self.db:
            return self.db.notes(investigation_id)
        return list(self._notes.get(investigation_id, []))

    def list(self, principal, filters: dict, page: int, page_size: int,
             sort: str) -> dict:
        if sort not in SORTS:
            raise ApiError("E_VALIDATION", "sort must be recent, oldest or name")
        if self.db:
            return self.db.list(principal, filters, page, page_size, sort)
        rows = [row for row in self._memory.values()
                if self._visible(principal, row) and _matches(row, filters)]
        rows.sort(key=lambda row: row["name"].lower() if sort == "name"
                  else row["opened_at"], reverse=sort == "recent")
        start = (page - 1) * page_size
        return {"items": rows[start:start + page_size], "page": page,
                "page_size": page_size, "total": len(rows),
                "pages": (len(rows) + page_size - 1) // page_size}

    def stats(self, principal, investigation_id: str) -> dict:
        self._authorize(principal, investigation_id)
        if self.db:
            return self.db.stats(investigation_id)
        scans = [record for record in self.scans._by_id.values()
                 if getattr(record, "investigation_id", None) == investigation_id]
        by_overall: dict[str, int] = {}
        for record in scans:
            if record.overall:
                by_overall[record.overall] = by_overall.get(record.overall, 0) + 1
        return {"investigation_id": investigation_id, "scan_count": len(scans),
                "evaluated_count": sum(by_overall.values()),
                "pending_count": len(scans) - sum(by_overall.values()),
                "by_overall": by_overall, "top_violations": []}

    def ensure_open(self, principal, investigation_id: str | None) -> str | None:
        """Validate a folder a scan is being filed into. Returns the id, or None."""
        if not investigation_id:
            return None
        row = self._authorize(principal, investigation_id)
        if row["status"] != "OPEN":
            raise ApiError("E_CONFLICT",
                           "this investigation is closed; reopen it to add a scan")
        return investigation_id

    # ---- internals -------------------------------------------------------------

    def _authorize(self, principal, investigation_id: str) -> dict:
        row = self.db.get(investigation_id) if self.db \
            else self._memory_get(investigation_id)
        if not self._visible(principal, row):
            raise ApiError("E_NOT_FOUND",
                           f"investigation {investigation_id} not found")
        return row

    def _visible(self, principal, row: dict) -> bool:
        if principal.disabled_auth or principal.role == "ADMIN":
            return True
        if self.db:      # the query is already scoped; a direct get needs the same rule
            return self.auth.jurisdiction_allows(principal, row["jurisdiction_id"])
        return (row["created_by"] == principal.id
                or row["jurisdiction_id"] == principal.jurisdiction_id)

    def _memory_create(self, principal, payload: dict) -> tuple[dict, bool]:
        client_uuid = payload.get("client_uuid")
        if client_uuid and client_uuid in self._by_client:
            return self._memory[self._by_client[client_uuid]], False
        now = datetime.now(UTC).isoformat()
        row = {"id": str(uuid.uuid4()), "client_uuid": client_uuid,
               "name": payload["name"], "subject_brand": payload.get("subject_brand"),
               "investigation_type": payload.get("investigation_type", "OTHER"),
               "location_text": payload.get("location_text"), "geo": None,
               "created_by": principal.id,
               "jurisdiction_id": payload["jurisdiction_id"],
               "status": "OPEN", "opened_at": now, "closed_at": None,
               "updated_at": now, "scan_count": 0, "failed_count": 0}
        self._memory[row["id"]] = row
        if client_uuid:
            self._by_client[client_uuid] = row["id"]
        return row, True

    def _memory_get(self, investigation_id: str) -> dict:
        row = self._memory.get(investigation_id)
        if row is None:
            raise ApiError("E_NOT_FOUND", f"investigation {investigation_id} not found")
        return row


def validate(values: dict, *, partial: bool = False) -> dict:
    name = (values.get("name") or "").strip()
    if not partial and not name:
        raise ApiError("E_VALIDATION", "an investigation needs a name")
    if len(name) > MAX_NAME:
        raise ApiError("E_VALIDATION", f"name must be at most {MAX_NAME} characters")
    kind = values.get("investigation_type")
    if kind is not None and kind not in TYPES:
        raise ApiError("E_VALIDATION", f"unsupported investigation_type: {kind}")
    status = values.get("status")
    if status is not None and status not in STATUSES:
        raise ApiError("E_VALIDATION", f"unsupported status: {status}")
    if values.get("client_uuid"):
        try:
            uuid.UUID(str(values["client_uuid"]))
        except ValueError as exc:
            raise ApiError("E_VALIDATION", "client_uuid must be a UUID") from exc
    cleaned = {k: v for k, v in values.items() if v is not None}
    if name:
        cleaned["name"] = name
    return cleaned


def _matches(row: dict, filters: dict) -> bool:
    for key in ("status", "investigation_type", "created_by"):
        if filters.get(key) and row.get(key) != filters[key]:
            return False
    needle = (filters.get("q") or "").lower()
    if needle:
        haystack = " ".join(str(row.get(k) or "") for k in
                            ("name", "subject_brand", "location_text")).lower()
        if needle not in haystack:
            return False
    return True
