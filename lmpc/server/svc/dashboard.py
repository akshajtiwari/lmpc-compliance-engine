"""Role-scoped operational aggregates for the local enforcement workbench."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select

from ..db.models import (ExtractedDeclaration, Manufacturer, Product, RuleEvaluation,
                         Scan, ScanImage)
from .store_records import evaluation_dict


class DashboardService:
    def __init__(self, scan_store, review_service):
        self.scans = scan_store
        self.review = review_service
        self.db = review_service.db

    def summary(self, principal) -> dict:
        rows = self._scans(principal)
        today = date.today()
        completed = [row for row in rows if row.overall]
        non_compliant = sum(row.overall == "NON_COMPLIANT" for row in completed)
        pending = sum(row.status in {"EVALUATION_COMPLETE", "UNDER_REVIEW"} for row in rows)
        return {
            "today": sum(_captured(row) == today for row in rows),
            "last_7_days": sum(_captured(row) >= today - timedelta(days=6) for row in rows),
            "last_30_days": sum(_captured(row) >= today - timedelta(days=29) for row in rows),
            "total": len(rows), "pending_reviews": pending,
            "non_compliant": non_compliant,
            "violation_rate": round(non_compliant / len(completed), 4) if completed else 0.0,
        }

    def violations(self, principal, limit: int = 20) -> list[dict]:
        counter = Counter()
        clauses = {}
        for row in self._effective_evaluations(principal):
            if row["outcome"] == "FAIL":
                counter[row["check"]] += 1
                clauses[row["check"]] = row["clause"]
        return [{"check": check, "clause": clauses[check], "count": count}
                for check, count in counter.most_common(limit)]

    def top_non_compliant(self, principal, limit: int = 10) -> list[dict]:
        if not self.db:
            return []
        statement = select(Manufacturer.name).select_from(Scan).join(
            Product, Product.id == Scan.product_id).join(
                Manufacturer, Manufacturer.id == Product.manufacturer_id).where(
                    Scan.overall == "NON_COMPLIANT")
        statement = self.db.scope_scans(statement, principal)
        with self.db.sessions() as session:
            counts = Counter(session.scalars(statement).all())
        return [{"manufacturer": name, "count": count}
                for name, count in counts.most_common(limit)]

    def geo(self, principal) -> list[dict]:
        rows = self._scans(principal)
        points = []
        for row in rows:
            latitude = _value(row, "geo_lat")
            longitude = _value(row, "geo_lng")
            if latitude is not None and longitude is not None:
                points.append({"lat": float(latitude), "lng": float(longitude),
                               "overall": row.overall, "count": 1})
        return points

    def quality(self, principal) -> dict:
        scans = self._scans(principal)
        evaluations = self._effective_evaluations(principal)
        overrides = sum(row.get("is_override", False) for row in evaluations)
        abstentions = sum(row["outcome"] in {"INDETERMINATE", "REVIEW_REQUIRED"}
                          for row in evaluations)
        coverage = {str(scan.id): scan.coverage_asserted for scan in scans}
        unsafe = sum(row["outcome"] == "FAIL" and not row.get("is_override", False)
                     and not coverage.get(row["scan_id"], False) for row in evaluations)
        extracted, images = self._evidence_counts(principal)
        return {
            "scans": len(scans), "images": images,
            "declarations_extracted": extracted,
            "declarations_per_scan": round(extracted / len(scans), 2) if scans else 0.0,
            "abstention_rate": round(abstentions / len(evaluations), 4)
            if evaluations else 0.0,
            "override_rate": round(overrides / len(evaluations), 4)
            if evaluations else 0.0,
            "false_accusation_guard_breaches": unsafe,
        }

    def _scans(self, principal) -> list:
        if self.db:
            statement = self.db.scope_scans(select(Scan), principal)
            with self.db.sessions() as session:
                return list(session.scalars(statement))
        return list(self.scans._by_id.values())

    def _effective_evaluations(self, principal) -> list[dict]:
        scans = self._scans(principal)
        if not scans:
            return []
        if not self.db:
            return [{**row, "scan_id": scan.id} for scan in scans
                    for row in scan.latest_evaluations()]
        ids = [scan.id for scan in scans]
        with self.db.sessions() as session:
            rows = list(session.scalars(select(RuleEvaluation).where(
                RuleEvaluation.scan_id.in_(ids)).order_by(
                    RuleEvaluation.batch, RuleEvaluation.evaluated_at,
                    RuleEvaluation.is_override, RuleEvaluation.id)))
        latest = {scan.id: 0 for scan in scans}
        for row in rows:
            latest[row.scan_id] = max(latest[row.scan_id], row.batch)
        effective = {}
        for row in rows:
            if row.batch == latest[row.scan_id]:
                effective[(row.scan_id, row.check_code)] = row
        return [{**evaluation_dict(row), "scan_id": str(row.scan_id)}
                for row in effective.values()]

    def _evidence_counts(self, principal) -> tuple[int, int]:
        scans = self._scans(principal)
        if not self.db:
            return (sum(len(scan.latest_declarations()) for scan in scans),
                    sum(len(scan.images) for scan in scans))
        ids = [scan.id for scan in scans]
        if not ids:
            return 0, 0
        with self.db.sessions() as session:
            images = len(list(session.scalars(select(ScanImage.id).where(
                ScanImage.scan_id.in_(ids)))))
            rows = list(session.scalars(select(ExtractedDeclaration).where(
                ExtractedDeclaration.scan_id.in_(ids)).order_by(
                    ExtractedDeclaration.batch, ExtractedDeclaration.created_at,
                    ExtractedDeclaration.id)))
        latest = {scan.id: 0 for scan in scans}
        for row in rows:
            latest[row.scan_id] = max(latest[row.scan_id], row.batch)
        effective = {(row.scan_id, row.field_type): row for row in rows
                     if row.batch == latest[row.scan_id]}
        return len(effective), images


def _captured(row) -> date:
    value = row.captured_at
    return value if isinstance(value, date) else date.fromisoformat(value)


def _value(row, name: str):
    """Read a column on ORM rows or the equivalent metadata on memory rows."""
    return getattr(row, name) if hasattr(row, name) else row.metadata.get(name)
