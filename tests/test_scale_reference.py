"""Scale-reference marks -> engine px_per_mm and panel dimensions."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from lmpc.engine.model import Token
from lmpc.lawc.build import load
from lmpc.server.svc.evidence import EvidenceImage
from lmpc.server.svc.object_store import LocalObjectStore
from lmpc.server.svc.pipeline import Pipeline
from lmpc.server.svc.scale import ID1_LONG_MM, ID1_SHORT_MM, engine_measurements
from lmpc.server.svc.scan_service import MemoryStore

PX_PER_MM = 12.0     # the synthetic photograph's scale


def _card_quad(px_per_mm=PX_PER_MM, tilt=0.0, origin=(60, 40)):
    """Card corner marks as the phone would send them, optionally tilted."""
    theta = np.deg2rad(tilt)
    pts = []
    for mm_x, mm_y in ((0.0, 0.0), (ID1_LONG_MM, 0.0), (ID1_LONG_MM, ID1_SHORT_MM),
                       (0.0, ID1_SHORT_MM)):
        # A tilt about the vertical axis foreshortens the card's long (x) edges.
        pts.append([round(origin[0] + mm_x * px_per_mm * np.cos(theta), 3),
                    round(origin[1] + mm_y * px_per_mm, 3)])
    return pts


def _panel_quad(width_mm=54.0, height_mm=86.0, origin=(700, 150),
                px_per_mm=PX_PER_MM, tilt=0.0):
    theta = np.deg2rad(tilt)
    return [[round(origin[0] + x * px_per_mm * np.cos(theta), 3),
             round(origin[1] + y * px_per_mm, 3)] for x, y in
            ((0.0, 0.0), (width_mm, 0.0), (width_mm, height_mm), (0.0, height_mm))]


def _meta(data=None, mode="PHYSICAL_PACKAGE", scale_type="ISO_ID1_CARD"):
    return {"mode": mode, "scale_reference_type": scale_type,
            "scale_reference_data": data}


def test_plain_long_edge_mark_sets_px_per_mm():
    out = engine_measurements("PHYSICAL_PACKAGE", _meta(data={"observed_px": 856.0}))
    assert out is not None and out.px_per_mm == pytest.approx(10.0)
    assert out.pdp_w_cm is None and out.pdp_h_cm is None


def test_card_and_panel_quads_yield_scale_and_physical_panel_size():
    out = engine_measurements(
        "PHYSICAL_PACKAGE", _meta(data={"quad": _card_quad(),
                                        "panel_quad": _panel_quad()}))
    assert out is not None
    assert out.px_per_mm == pytest.approx(PX_PER_MM, rel=1e-3)
    assert out.pdp_w_cm == pytest.approx(5.4, rel=1e-3)
    assert out.pdp_h_cm == pytest.approx(8.6, rel=1e-3)


def test_tilted_capture_is_perspective_corrected():
    # Under a 30-degree tilt the naive long-edge reading under-measures by
    # cos(30). The homography path measures scale as the area-average over the
    # panel plane (12 * sqrt(cos 30) for this synthetic camera) and, decisively,
    # recovers the panel's true physical size from the foreshortened marks.
    out = engine_measurements(
        "PHYSICAL_PACKAGE", _meta(data={"quad": _card_quad(tilt=30.0),
                                        "panel_quad": _panel_quad(tilt=30.0)}))
    assert out is not None
    assert out.px_per_mm == pytest.approx(PX_PER_MM * np.sqrt(np.cos(np.deg2rad(30.0))),
                                          rel=1e-3)
    assert out.px_per_mm > PX_PER_MM * np.cos(np.deg2rad(30.0))   # beats the naive edge
    assert out.pdp_w_cm == pytest.approx(5.4, rel=1e-2)
    assert out.pdp_h_cm == pytest.approx(8.6, rel=1e-2)


def test_marking_the_wrong_object_abstains():
    square = [[60, 40], [400, 40], [400, 380], [60, 380]]
    assert engine_measurements("PHYSICAL_PACKAGE", _meta(data={"quad": square})) is None


def test_degenerate_and_non_convex_quads_abstain():
    line = [[60, 40], [400, 40], [60, 40], [400, 40]]
    bowtie = [[60, 40], [400, 380], [400, 40], [60, 380]]
    for quad in (line, bowtie):
        assert engine_measurements("PHYSICAL_PACKAGE", _meta(data={"quad": quad})) is None


def test_absurd_long_edge_abstains():
    assert engine_measurements("PHYSICAL_PACKAGE",
                               _meta(data={"observed_px": 4.0})) is None


def test_skewed_panel_plane_abstains_instead_of_guessing():
    # The panel quad is not parallel to the card plane: its local px/mm varies
    # widely between edges, so a single scale number would be a fabrication.
    skewed = [[200, 150], [448, 300], [448, 560], [200, 470]]
    out = engine_measurements(
        "PHYSICAL_PACKAGE", _meta(data={"quad": _card_quad(),
                                        "panel_quad": skewed}))
    assert out is None


def test_listing_mode_never_receives_scale():
    assert engine_measurements(
        "ECOMMERCE_LISTING", _meta(mode="ECOMMERCE_LISTING",
                                   data={"observed_px": 856.0})) is None


def test_garbage_scale_data_abstains_without_raising():
    for data in (None, 12, "quad", {"quad": "junk"}, {"observed_px": "junk"},
                 {"quad": [[1, 2], [3, 4], [5]]}):
        assert engine_measurements("PHYSICAL_PACKAGE", _meta(data=data)) is None


def test_pipeline_feeds_the_scale_reference_into_the_geometry_check():
    # 856 px long edge -> 10 px/mm; the MRP glyph is 250 px tall = 25.0 mm.
    scans, objects, rec = _ready_scan(
        {"scale_reference_type": "ISO_ID1_CARD",
         "scale_reference_data": {"observed_px": 856.0},
         "pdp_h_cm": 8.6, "pdp_w_cm": 5.4})
    completed = Pipeline(scans, objects, load(), 1800, reader=_big_mrp_reader) \
        .process(rec.id)
    min_height = next(item for item in completed.latest_evaluations()
                      if item["check"] == "LMPC-R7-2-MIN-HEIGHT")
    assert min_height["outcome"] == "PASS"
    assert min_height["evidence"].get("measured_mm") == pytest.approx(25.0, rel=1e-3)


def test_without_scale_the_geometry_check_abstains():
    scans, objects, rec = _ready_scan(
        {"pdp_h_cm": 8.6, "pdp_w_cm": 5.4})
    completed = Pipeline(scans, objects, load(), 1800, reader=_big_mrp_reader) \
        .process(rec.id)
    min_height = next(item for item in completed.latest_evaluations()
                      if item["check"] == "LMPC-R7-2-MIN-HEIGHT")
    assert min_height["outcome"] == "INDETERMINATE"
    assert "no scale reference" in min_height["reason"]


def _ready_scan(metadata):
    data = b"validated-image-bytes"
    digest = hashlib.sha256(data).hexdigest()
    image = EvidenceImage(
        filename="front.jpg", media_type="image/jpeg", data=b"", sha256=digest,
        width_px=1200, height_px=800, storage_key=f"images/{digest}.jpg",
        panel_label="FRONT")
    objects = LocalObjectStore("/tmp/lmpc-scale-test-objects")
    objects.put_immutable(image.storage_key, data, image.media_type, digest)
    scans = MemoryStore()
    rec, _ = scans.create(
        client_uuid="20000000-0000-4000-8000-000000000001",
        captured_at="2026-09-07", mode="PHYSICAL_PACKAGE", category="FOOD",
        coverage_asserted=False, panels=["FRONT"], images=[image],
        metadata=metadata)
    return scans, objects, rec


def _big_mrp_reader(_data, *, panel, **_kwargs):
    return [
        Token("MRP Rs. 45.00 (incl. of all taxes)", 10, 20, 310, 250,
              conf=0.99, panel=panel),
        Token("Net Qty 500 g", 10, 320, 180, 250, conf=0.99, panel=panel),
    ]
