"""The stored-image to deterministic-verdict orchestration path."""
from __future__ import annotations

import hashlib

import pytest

from lmpc.engine.model import Token
from lmpc.lawc.build import load
from lmpc.server.svc.evidence import EvidenceImage
from lmpc.server.svc.object_store import LocalObjectStore
from lmpc.server.svc.pipeline import Pipeline
from lmpc.server.svc.scan_service import MemoryStore


def _ready_scan(tmp_path, category="FOOD"):
    data = b"validated-image-bytes"
    digest = hashlib.sha256(data).hexdigest()
    image = EvidenceImage(
        filename="front.jpg", media_type="image/jpeg", data=b"", sha256=digest,
        width_px=1200, height_px=800, storage_key=f"images/{digest}.jpg",
        panel_label="FRONT")
    objects = LocalObjectStore(tmp_path)
    objects.put_immutable(image.storage_key, data, image.media_type, digest)
    scans = MemoryStore()
    rec, _ = scans.create(
        client_uuid="10000000-0000-4000-8000-000000000001",
        captured_at="2026-09-07", mode="PHYSICAL_PACKAGE", category=category,
        coverage_asserted=False, panels=["FRONT"], images=[image])
    return scans, objects, rec


def _reader(_data, *, panel, **_kwargs):
    return [
        Token("MRP Rs. 45.00 (incl. of all taxes)", 10, 20, 310, 24,
              conf=0.99, panel=panel),
        Token("Net Qty 500 g", 10, 70, 180, 24, conf=0.99, panel=panel),
    ]


def test_pipeline_persists_explanations_and_full_rulepack_identity(tmp_path):
    scans, objects, rec = _ready_scan(tmp_path)
    completed = Pipeline(scans, objects, load(), 1800, reader=_reader).process(rec.id)

    assert completed.status == "EVALUATION_COMPLETE"
    assert completed.batch == 1 and completed.overall == "INCOMPLETE_EVIDENCE"
    assert len(completed.rulepack_sha256) == 64
    mrp = next(item for item in completed.latest_declarations() if item["field"] == "mrp")
    assert mrp["bbox"] == [10, 20, 310, 24]
    assert mrp["feature_weights"]["anchor"] == 40.0
    assert len(completed.latest_evaluations()) == 21
    assert all(item["citation"] for item in completed.latest_evaluations())
    assert completed.images[0].max_edge_used == 1200


def test_reevaluation_appends_instead_of_replacing_the_prior_batch(tmp_path):
    scans, objects, rec = _ready_scan(tmp_path)
    pipeline = Pipeline(scans, objects, load(), 1800, reader=_reader)
    pipeline.process(rec.id)
    completed = pipeline.process(rec.id)

    assert completed.batch == 2
    assert {item["batch"] for item in completed.evaluations} == {1, 2}
    assert len(completed.evaluations) == 42


def test_ocr_failure_marks_the_scan_failed_without_a_legal_finding(tmp_path):
    scans, objects, rec = _ready_scan(tmp_path)

    def broken(*_args, **_kwargs):
        raise RuntimeError("recogniser unavailable")

    with pytest.raises(RuntimeError, match="recogniser unavailable"):
        Pipeline(scans, objects, load(), 1800, reader=broken).process(rec.id)
    failed = scans.get(rec.id)
    assert failed.status == "FAILED"
    assert failed.evaluations == []
    assert failed.failure_reason == "RuntimeError: recogniser unavailable"


def test_applicability_gate_stops_an_exempt_scan_before_ocr(tmp_path):
    scans, objects, rec = _ready_scan(tmp_path, category="DRUG_FORMULATION")

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("OCR ran for a package outside these rules")

    completed = Pipeline(scans, objects, load(), 1800, reader=must_not_run).process(rec.id)
    assert completed.overall == "OUT_OF_SCOPE"
    assert completed.declarations == []
    assert completed.images[0].max_edge_used is None
    assert all(item["outcome"] == "NOT_APPLICABLE" for item in completed.evaluations)
