"""PDF/DOCX finalization from one versioned verdict snapshot."""
from __future__ import annotations

import hashlib
import io

import pytest
from docx import Document

from lmpc.engine.model import Token
from lmpc.lawc.build import load
from lmpc.server.api.errors import ApiError
from lmpc.server.svc.evidence import EvidenceImage
from lmpc.server.svc.object_store import LocalObjectStore
from lmpc.server.svc.pipeline import Pipeline
from lmpc.server.svc.reporting import ReportService
from lmpc.server.svc.scan_service import MemoryStore


def _evaluated(tmp_path):
    raw = b"report-source-image"
    digest = hashlib.sha256(raw).hexdigest()
    image = EvidenceImage(
        filename="front.jpg", media_type="image/jpeg", data=b"", sha256=digest,
        width_px=800, height_px=600, storage_key=f"images/{digest}.jpg",
        panel_label="FRONT")
    objects = LocalObjectStore(tmp_path)
    objects.put_immutable(image.storage_key, raw, image.media_type, digest)
    scans = MemoryStore()
    scan, _ = scans.create(
        client_uuid="20000000-0000-4000-8000-000000000001",
        captured_at="2026-09-07", mode="PHYSICAL_PACKAGE", category="FOOD",
        coverage_asserted=False, panels=["FRONT"], images=[image])

    def reader(_data, *, panel, **_kwargs):
        return [Token("MRP Rs. 45.00 (incl. of all taxes)", 10, 20, 300, 20,
                      conf=0.99, panel=panel)]

    pack = load()
    Pipeline(scans, objects, pack, 1800, reader=reader).process(scan.id)
    return scans, objects, pack, scan.id


def _document_text(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return "\n".join(paragraphs + cells)


def test_both_formats_are_stored_with_the_same_finding_set_and_content_hash(tmp_path):
    scans, objects, pack, scan_id = _evaluated(tmp_path)
    reports = ReportService(scans, objects, pack, max_edge=1800, git_sha="abc123")
    report = reports.finalize(scan_id)
    pdf, _, _ = reports.download(report["id"], "pdf")
    docx, _, _ = reports.download(report["id"], "docx")

    assert pdf.startswith(b"%PDF-") and docx.startswith(b"PK")
    text = _document_text(docx)
    for evaluation in scans.get(scan_id).latest_evaluations():
        assert evaluation["check"] in text
        assert evaluation["clause"] in text
    assert report["content_sha256"] in text
    assert report["manifest"]["rulepack"]["sha256"] == pack["sha256"]
    assert report["manifest"]["inputs"][0]["sha256"]


def test_refinalizing_retains_version_one_and_uses_a_stable_content_hash(tmp_path):
    scans, objects, pack, scan_id = _evaluated(tmp_path)
    reports = ReportService(scans, objects, pack, max_edge=1800)
    first, second = reports.finalize(scan_id), reports.finalize(scan_id)
    assert (first["version"], second["version"]) == (1, 2)
    assert first["id"] != second["id"]
    assert first["content_sha256"] == second["content_sha256"]
    assert scans.get_report(first["id"])["version"] == 1


def test_system_error_blocks_finalization(tmp_path):
    scans, objects, pack, scan_id = _evaluated(tmp_path)
    scan = scans.get(scan_id)
    scan.evaluations[-1]["outcome"] = "SYSTEM_ERROR"
    with pytest.raises(ApiError, match="SYSTEM_ERROR") as raised:
        ReportService(scans, objects, pack, max_edge=1800).finalize(scan_id)
    assert raised.value.code == "E_CONFLICT"
