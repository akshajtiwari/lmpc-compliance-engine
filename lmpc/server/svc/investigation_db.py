"""SQL behind investigations: the folder, its scans, and its running totals."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select

from ..api.errors import ApiError
from ..db.investigations import Investigation, InvestigationNote
from ..db.models import Jurisdiction, RuleEvaluation, Scan, User
from ..db.paths import contains
from ..db.upsert import insert_ignore

SORTS = {"recent": Investigation.opened_at.desc(),
         "oldest": Investigation.opened_at.asc(),
         "name": Investigation.name.asc()}


class InvestigationDb:
    def __init__(self, scan_store):
        self.sessions = scan_store.sessions
        self.dialect = self.sessions.kw["bind"].dialect.name

    # ---- writes ----------------------------------------------------------------

    def create(self, principal, values: dict) -> tuple[dict, bool]:
        """Idempotent on client_uuid: a retried create returns the original folder.

        The phone may create a folder with no network and retry for an hour. Without this
        the officer would come back online to five copies of the same investigation.
        """
        with self.sessions() as session:
            row = insert_ignore(
                session, Investigation,
                values=dict(client_uuid=values.get("client_uuid"),
                            name=values["name"],
                            subject_brand=values.get("subject_brand"),
                            investigation_type=values.get("investigation_type", "OTHER"),
                            location_text=values.get("location_text"),
                            geo_lat=values.get("geo_lat"), geo_lng=values.get("geo_lng"),
                            created_by=uuid.UUID(principal.id),
                            jurisdiction_id=uuid.UUID(values["jurisdiction_id"])),
                index_elements=[Investigation.client_uuid],
                returning=Investigation.id)
            if row is None:
                session.commit()
                existing = session.scalar(select(Investigation).where(
                    Investigation.client_uuid == values["client_uuid"]))
                return _public(existing), False
            session.commit()
            return _public(session.get(Investigation, row[0])), True

    def update(self, investigation_id: str, values: dict) -> dict:
        with self.sessions() as session:
            row = self._row(session, investigation_id)
            for field in ("name", "subject_brand", "investigation_type",
                          "location_text", "status"):
                if values.get(field) is not None:
                    setattr(row, field, values[field])
            if values.get("status") == "CLOSED" and row.closed_at is None:
                row.closed_at = datetime.now(UTC)
            if values.get("status") == "OPEN":
                row.closed_at = None
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return _public(row)

    def add_note(self, investigation_id: str, principal, body: str,
                 storage_key: str | None, sha256: str | None) -> dict:
        with self.sessions() as session:
            self._row(session, investigation_id)
            note = InvestigationNote(
                investigation_id=uuid.UUID(investigation_id),
                author_id=uuid.UUID(principal.id), body=body,
                storage_key=storage_key, sha256=sha256)
            session.add(note)
            session.commit()
            session.refresh(note)
            return _note(note, principal.full_name)

    # ---- reads -----------------------------------------------------------------

    def get(self, investigation_id: str) -> dict:
        with self.sessions() as session:
            return _public(self._row(session, investigation_id))

    def notes(self, investigation_id: str) -> list[dict]:
        with self.sessions() as session:
            self._row(session, investigation_id)
            rows = session.execute(
                select(InvestigationNote, User.full_name)
                .join(User, User.id == InvestigationNote.author_id)
                .where(InvestigationNote.investigation_id == uuid.UUID(investigation_id))
                .order_by(InvestigationNote.created_at.desc())).all()
            return [_note(note, author) for note, author in rows]

    def list(self, principal, filters: dict, page: int, page_size: int,
             sort: str) -> dict:
        with self.sessions() as session:
            statement = self.scope(select(Investigation), principal)
            statement = self._filters(statement, filters)
            total = session.scalar(select(func.count()).select_from(
                statement.subquery())) or 0
            rows = session.scalars(
                statement.order_by(SORTS[sort])
                .offset((page - 1) * page_size).limit(page_size)).all()
            items = [_public(row) for row in rows]
            counts = self._scan_counts(session, [row.id for row in rows])
            for item in items:
                item.update(counts.get(uuid.UUID(item["id"]),
                                       {"scan_count": 0, "failed_count": 0}))
            return {"items": items, "page": page, "page_size": page_size,
                    "total": total, "pages": (total + page_size - 1) // page_size}

    def stats(self, investigation_id: str) -> dict:
        """Derived on every read, never denormalised into a counter column.

        A counter drifts the moment a reviewer overrides a verdict or a re-evaluation
        batch lands — and drift is exactly what this product cannot have.
        """
        target = uuid.UUID(investigation_id)
        with self.sessions() as session:
            self._row(session, investigation_id)
            by_overall = dict(session.execute(
                select(Scan.overall, func.count()).where(
                    Scan.investigation_id == target).group_by(Scan.overall)).all())
            total = sum(by_overall.values())
            evaluated = total - by_overall.get(None, 0)
            top = session.execute(
                select(RuleEvaluation.check_code, func.count().label("n"))
                .join(Scan, Scan.id == RuleEvaluation.scan_id)
                .where(Scan.investigation_id == target,
                       RuleEvaluation.outcome == "FAIL",
                       RuleEvaluation.is_override.is_(False))
                .group_by(RuleEvaluation.check_code)
                .order_by(func.count().desc()).limit(3)).all()
            return {
                "investigation_id": investigation_id,
                "scan_count": total,
                "evaluated_count": evaluated,
                "pending_count": by_overall.get(None, 0),
                "by_overall": {k: v for k, v in by_overall.items() if k},
                "top_violations": [{"check": code, "count": n} for code, n in top],
            }

    # ---- scoping ---------------------------------------------------------------

    def scope(self, statement, principal):
        """Jurisdiction, not officer.

        A field officer sees only their own *scans*, but an investigation is a shared
        case file: two officers working the same market must both be able to open it.
        """
        if principal.disabled_auth or principal.role == "ADMIN":
            return statement
        if not principal.jurisdiction_id:
            return statement.where(Investigation.created_by == uuid.UUID(principal.id))
        root_path = select(Jurisdiction.path).where(
            Jurisdiction.id == uuid.UUID(principal.jurisdiction_id)).scalar_subquery()
        descendants = select(Jurisdiction.id).where(
            contains(self.dialect, Jurisdiction.path, root_path))
        return statement.where(Investigation.jurisdiction_id.in_(descendants))

    def _filters(self, statement, values: dict):
        for key, column in (("status", Investigation.status),
                            ("investigation_type", Investigation.investigation_type),
                            ("created_by", Investigation.created_by)):
            if values.get(key) is not None:
                statement = statement.where(column == values[key])
        if values.get("q"):
            needle = f"%{values['q']}%"
            statement = statement.where(or_(
                Investigation.name.ilike(needle),
                Investigation.subject_brand.ilike(needle),
                Investigation.location_text.ilike(needle)))
        return statement

    def _scan_counts(self, session, ids: list) -> dict:
        """Scan and failure totals for a page of folders, in one grouped query."""
        if not ids:
            return {}
        rows = session.execute(
            select(Scan.investigation_id, Scan.overall, func.count())
            .where(Scan.investigation_id.in_(ids))
            .group_by(Scan.investigation_id, Scan.overall))
        counts: dict = {}
        for investigation_id, outcome, n in rows:
            bucket = counts.setdefault(investigation_id,
                                       {"scan_count": 0, "failed_count": 0})
            bucket["scan_count"] += n
            if outcome == "NON_COMPLIANT":
                bucket["failed_count"] += n
        return counts

    def _row(self, session, investigation_id: str) -> Investigation:
        try:
            row = session.get(Investigation, uuid.UUID(investigation_id))
        except ValueError:
            row = None
        if row is None:
            raise ApiError("E_NOT_FOUND", f"investigation {investigation_id} not found")
        return row


def _public(row: Investigation) -> dict:
    return {
        "id": str(row.id),
        "client_uuid": str(row.client_uuid) if row.client_uuid else None,
        "name": row.name, "subject_brand": row.subject_brand,
        "investigation_type": row.investigation_type,
        "location_text": row.location_text,
        "geo": ({"lat": float(row.geo_lat), "lng": float(row.geo_lng)}
                if row.geo_lat is not None and row.geo_lng is not None else None),
        "created_by": str(row.created_by),
        "jurisdiction_id": str(row.jurisdiction_id),
        "status": row.status,
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _note(row: InvestigationNote, author: str | None) -> dict:
    return {"id": str(row.id), "body": row.body, "author": author,
            "author_id": str(row.author_id), "storage_key": row.storage_key,
            "sha256": row.sha256,
            "created_at": row.created_at.isoformat() if row.created_at else None}
