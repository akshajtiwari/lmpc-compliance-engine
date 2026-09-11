"""Stored evidence -> OCR -> extraction -> deterministic evaluation.

This module orchestrates existing components; it contains no legal thresholds. A failed
OCR run marks the scan failed and never fabricates a compliance finding.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from lmpc.engine import ocr
from lmpc.engine.engine import FIELD_KINDS, run, run_gates
from lmpc.engine.extract import extract
from lmpc.engine.model import Field, Scan, Token

from ..obs import metrics
from .object_store import ObjectStore
from .scale import engine_measurements
from .scan_service import ScanRecord

Reader = Callable[..., list[Token]]
CorrectionReader = Callable[[str], list[dict[str, Any]]]


class Pipeline:
    def __init__(self, scan_store, object_store: ObjectStore, rulepack: dict,
                 max_edge: int, reader: Reader | None = None,
                 corrections: CorrectionReader | None = None):
        self.scans = scan_store
        self.objects = object_store
        self.rulepack = rulepack
        self.max_edge = max_edge
        self.reader = reader or ocr.read_bytes
        self.corrections = corrections or (lambda _scan_id: [])

    def process(self, scan_id: str) -> ScanRecord:
        started = time.perf_counter()
        rec = self.scans.start_processing(scan_id)
        try:
            scan = _engine_scan(rec, [])
            stop_effects = {"ALL_RULES_NOT_APPLICABLE", "CHAPTER_II_NOT_APPLICABLE"}
            if any(gate["effect"] in stop_effects for gate in run_gates(self.rulepack, scan)):
                result = run(self.rulepack, scan)
                saved = self.scans.complete_evaluation(
                    scan_id, declarations=[], evaluations=_evaluations(result, self.rulepack),
                    overall=result["overall"], rulepack_version=self.rulepack["version"],
                    rulepack_sha256=self.rulepack["sha256"], max_edges={})
                _record_metrics(saved)
                return saved
            tokens = _listing_tokens(rec)
            ocr_started = time.perf_counter()
            for image in rec.images:
                data = self.objects.read(image.storage_key)
                tokens.extend(self.reader(
                    data, panel=image.panel_label, min_conf=0.0, max_edge=self.max_edge))
            metrics.observe_stage("ocr", time.perf_counter() - ocr_started)
            scan = _engine_scan(rec, tokens)
            extraction_started = time.perf_counter()
            fields = extract(scan, FIELD_KINDS)
            corrected = {item["field"]: item for item in self.corrections(scan_id)}
            _apply_corrections(fields, corrected)
            metrics.observe_stage("extraction", time.perf_counter() - extraction_started)
            evaluation_started = time.perf_counter()
            result = run(self.rulepack, scan, fields)
            metrics.observe_stage("evaluation", time.perf_counter() - evaluation_started)
            saved = self.scans.complete_evaluation(
                scan_id, declarations=_declarations(fields, corrected),
                evaluations=_evaluations(result, self.rulepack), overall=result["overall"],
                rulepack_version=self.rulepack["version"],
                rulepack_sha256=self.rulepack["sha256"],
                max_edges={image.storage_key: min(
                    max(image.width_px, image.height_px), self.max_edge)
                    for image in rec.images})
            _record_metrics(saved)
            return saved
        except Exception as exc:
            self.scans.fail_processing(scan_id, f"{type(exc).__name__}: {exc}")
            raise
        finally:
            metrics.observe_stage("total", time.perf_counter() - started)


def _engine_scan(rec: ScanRecord, tokens: list[Token]) -> Scan:
    meta = rec.metadata
    scale = engine_measurements(rec.mode, meta)
    # A marked scale reference beats a bare client number: it was measured against
    # a pinned physical artefact and carries the perspective guards with it.
    px_per_mm = meta.get("px_per_mm")
    pdp_h_cm, pdp_w_cm = meta.get("pdp_h_cm"), meta.get("pdp_w_cm")
    if scale is not None:
        measurements = scale.as_meta()
        px_per_mm = measurements["px_per_mm"]
        # Officer-typed dimensions remain authoritative when both exist; the card
        # measurement fills the panel size only where nobody measured it directly.
        pdp_h_cm = pdp_h_cm if pdp_h_cm is not None else measurements.get("pdp_h_cm")
        pdp_w_cm = pdp_w_cm if pdp_w_cm is not None else measurements.get("pdp_w_cm")
    return Scan(
        tokens=tokens, captured_at=rec.captured_at,
        panels_captured=set(rec.panels), mode=rec.mode, category=rec.category,
        buyer_type=meta.get("buyer_type", "RETAIL"),
        is_imported=meta.get("is_imported", False), is_molded=meta.get("is_molded", False),
        other_law_requires_same_info=meta.get("other_law_requires_same_info", False),
        package_shape=meta.get("package_shape", "RECTANGULAR"),
        px_per_mm=px_per_mm, pdp_h_cm=pdp_h_cm, pdp_w_cm=pdp_w_cm,
        net_quantity_g=meta.get("net_quantity_g"),
        net_quantity_ml=meta.get("net_quantity_ml"), capacity_cm3=meta.get("capacity_cm3"),
        coverage_asserted=rec.coverage_asserted,
    )


def _listing_tokens(rec: ScanRecord) -> list[Token]:
    """Treat officer-pasted listing text as listing evidence, never as package OCR.

    Rule 6(10) explicitly governs what is displayed online. Geometry here is synthetic
    and therefore all typography/placement checks remain excluded by the listing mode.
    """
    if rec.mode != "ECOMMERCE_LISTING":
        return []
    text = (rec.metadata.get("ecommerce_text") or "").strip()
    if not text:
        return []
    lines = [line.strip() for line in re.split(
        r"(?:\r?\n|(?<=[.;])\s+(?=[A-Z]))", text) if line.strip()]
    return [Token(
        line, x=0, y=index * 28, w=max(8, min(1600, len(line) * 8)), h=22,
        conf=1.0, panel="LISTING", src=frozenset({f"listing:{index}"}))
        for index, line in enumerate(lines)]


def _apply_corrections(fields: dict[str, Field | None], corrections: dict[str, dict]) -> None:
    for kind, item in corrections.items():
        x, y, width, height = item["bbox"]
        token = Token(
            item["text"], x=x, y=y, w=width, h=height, conf=1.0,
            panel=item.get("panel") or "FRONT", cap_height_px=height,
            src=frozenset(item.get("source_token_ids") or [f"correction:{item['id']}"]))
        normalized = dict(item.get("normalized_value") or {})
        normalized["_features"] = {"officer_correction": 100.0}
        fields[kind] = Field(kind=kind, text=item["text"], tokens=[token],
                             score=100.0, margin=100.0, normalized=normalized)


def _declarations(fields: dict[str, Field | None],
                  corrections: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    corrections = corrections or {}
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
        item = {
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
        }
        if kind in corrections:
            item["corrected_by"] = corrections[kind]["corrected_by"]
        out.append(item)
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


def _record_metrics(record: ScanRecord) -> None:
    for field in record.latest_declarations():
        metrics.inc("lmpc_field_extracted_total", field=field["field"])
    for result in record.latest_evaluations():
        metrics.inc_verdict(result["outcome"], record.coverage_asserted, result["check"])
