"""Shared scan response envelope and JSON form-field parsing."""
from __future__ import annotations
import json

from ..svc.rule_help import decision_explanation
from .errors import ApiError


def envelope(rec, created: bool) -> dict:
    body = {"scan_id": rec.id, "status": rec.status,
            "client_uuid": rec.client_uuid, "officer_id": rec.officer_id,
            "jurisdiction_id": rec.jurisdiction_id,
            "status_url": f"/api/v1/scans/{rec.id}",
            "coverage_asserted": rec.coverage_asserted,
            "panels_captured": rec.panels,
            "captured_at": rec.captured_at, "mode": rec.mode, "category": rec.category,
            "buyer_type": rec.metadata.get("buyer_type", "RETAIL"),
            "package_shape": rec.metadata.get("package_shape", "RECTANGULAR"),
            "ecommerce": ({
                "url": rec.metadata.get("ecommerce_url"),
                "listing_text": rec.metadata.get("ecommerce_text"),
            } if rec.mode == "ECOMMERCE_LISTING" else None),
            "dimensions": {"h_cm": rec.metadata.get("pdp_h_cm"),
                           "w_cm": rec.metadata.get("pdp_w_cm"),
                           "capacity_cm3": rec.metadata.get("capacity_cm3")},
            "overall": rec.overall,
            "decision_explanation": decision_explanation(rec),
            "rulepack": ({"version": rec.rulepack_version,
                          "sha256": rec.rulepack_sha256}
                         if rec.rulepack_version else None),
            "images": [{"panel": image.panel_label, "storage_key": image.storage_key,
                        "sha256": image.sha256, "width": image.width_px,
                        "height": image.height_px, "max_edge_used": image.max_edge_used,
                        "quality": image.quality,
                        "url": f"/api/v1/scans/{rec.id}/images/{image.panel_label}"}
                       for image in rec.images],
            "declarations": rec.latest_declarations(),
            "evaluations": rec.latest_evaluations()}
    if rec.failure_reason:
        body["failure_reason"] = rec.failure_reason
    if not created:
        body["duplicate_ignored"] = True
    return body


def json_object(raw: str | None, field: str) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError("E_VALIDATION", f"{field} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ApiError("E_VALIDATION", f"{field} must be a JSON object")
    return value
