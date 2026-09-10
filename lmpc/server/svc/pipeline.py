"""Stored evidence -> OCR -> extraction -> deterministic evaluation.

This module orchestrates existing components; it contains no legal thresholds. A failed
OCR run marks the scan failed and never fabricates a compliance finding.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lmpc.engine import ocr
from lmpc.engine.engine import FIELD_KINDS, run, run_gates
from lmpc.engine.extract import extract
from lmpc.engine.model import Field, Scan, Token

from .object_store import ObjectStore
from .scan_service import ScanRecord

Reader = Callable[..., list[Token]]


class Pipeline:
    def __init__(self, scan_store, object_store: ObjectStore, rulepack: dict,
                 max_edge: int, reader: Reader | None = None):
        self.scans = scan_store
        self.objects = object_store
        self.rulepack = rulepack
        self.max_edge = max_edge
        self.reader = reader or ocr.read_bytes

    def process(self, scan_id: str) -> ScanRecord:
        rec = self.scans.start_processing(scan_id)
        try:
            scan = _engine_scan(rec, [])
            stop_effects = {"ALL_RULES_NOT_APPLICABLE", "CHAPTER_II_NOT_APPLICABLE"}
            if any(gate["effect"] in stop_effects for gate in run_gates(self.rulepack, scan)):
                result = run(self.rulepack, scan)
                return self.scans.complete_evaluation(
                    scan_id, declarations=[], evaluations=_evaluations(result, self.rulepack),
                    overall=result["overall"], rulepack_version=self.rulepack["version"],
                    rulepack_sha256=self.rulepack["sha256"], max_edges={})
            tokens = []
            for image in rec.images:
                data = self.objects.read(image.storage_key)
                tokens.extend(self.reader(
                    data, panel=image.panel_label, min_conf=0.0, max_edge=self.max_edge))
            scan = _engine_scan(rec, tokens)
            fields = extract(scan, FIELD_KINDS)
            result = run(self.rulepack, scan, fields)
            return self.scans.complete_evaluation(
                scan_id, declarations=_declarations(fields),
                evaluations=_evaluations(result, self.rulepack), overall=result["overall"],
                rulepack_version=self.rulepack["version"],
                rulepack_sha256=self.rulepack["sha256"],
                max_edges={image.storage_key: min(
                    max(image.width_px, image.height_px), self.max_edge)
                    for image in rec.images})
        except Exception as exc:
            self.scans.fail_processing(scan_id, f"{type(exc).__name__}: {exc}")
            raise


def _engine_scan(rec: ScanRecord, tokens: list[Token]) -> Scan:
    meta = rec.metadata
    return Scan(
        tokens=tokens, captured_at=rec.captured_at,
        panels_captured=set(rec.panels), mode=rec.mode, category=rec.category,
        buyer_type=meta.get("buyer_type", "RETAIL"),
        is_imported=meta.get("is_imported", False), is_molded=meta.get("is_molded", False),
        other_law_requires_same_info=meta.get("other_law_requires_same_info", False),
        package_shape=meta.get("package_shape", "RECTANGULAR"),
        px_per_mm=meta.get("px_per_mm"), pdp_h_cm=meta.get("pdp_h_cm"),
        pdp_w_cm=meta.get("pdp_w_cm"), net_quantity_g=meta.get("net_quantity_g"),
        net_quantity_ml=meta.get("net_quantity_ml"), capacity_cm3=meta.get("capacity_cm3"),
        coverage_asserted=rec.coverage_asserted,
    )


def _declarations(fields: dict[str, Field | None]) -> list[dict[str, Any]]:
    out = []
    for kind, field in fields.items():
        if field is None:
            continue
        tokens = field.tokens
        left = min(token.x for token in tokens)
        top = min(token.y for token in tokens)
        right = max(token.x + token.w for token in tokens)
        bottom = max(token.y + token.h for token in tokens)
        normalized = {key: value for key, value in field.normalized.items()
                      if not key.startswith("_")}
        out.append({
            "field": kind, "text": field.text, "normalized_value": normalized,
            "bbox": [left, top, right - left, bottom - top],
            "confidence": min(token.conf for token in tokens),
            "score": field.score, "margin": field.margin,
            "feature_weights": field.normalized.get("_features", {}),
            "source_token_ids": sorted(set().union(*(token.src for token in tokens))),
            "is_composite": any(len(token.src) > 1 for token in tokens),
            "is_repaired": any(token.repaired for token in tokens),
            "glyph_height_px": max((token.cap_height_px or token.h) for token in tokens),
            "panel": field.panel,
        })
    return out


def _evaluations(result: dict, pack: dict) -> list[dict[str, Any]]:
    specs = {item["check"]: item for item in pack["checks"]}
    out = []
    for evaluation in result["results"]:
        spec = specs[evaluation.check]
        params = spec.get("params") or {}
        out.append({
            "check": evaluation.check, "clause": evaluation.clause,
            "outcome": evaluation.verdict.value, "reason": evaluation.reason,
            "citation": evaluation.citation, "evidence": evaluation.evidence,
            "law_version": evaluation.evidence.get("law_version")
                           or spec.get("effective_from"),
            "field": spec.get("field") or params.get("field"),
        })
    return out
