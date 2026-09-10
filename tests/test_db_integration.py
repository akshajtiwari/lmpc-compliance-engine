"""PostgreSQL dialect integration; skipped unless LMPC_TEST_DB_URL is supplied."""
from __future__ import annotations

import hashlib
import io
import json
import os
import uuid

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select

from lmpc.engine.model import Token
from lmpc.server.config import Settings
from lmpc.server.db import sessionmaker_of
from lmpc.server.db.models import (AuditLog, ComplianceReport, ExtractedDeclaration,
                                   Jurisdiction, RuleEvaluation, User)
from lmpc.server.main import create_app
from lmpc.server.svc.auth_core import hash_password

DB_URL = os.environ.get("LMPC_TEST_DB_URL", "")
pytestmark = [pytest.mark.anyio,
              pytest.mark.skipif(not DB_URL, reason="set LMPC_TEST_DB_URL")]


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def database_app(tmp_path_factory):
    jurisdiction_id, officer_id = uuid.uuid4(), uuid.uuid4()
    with sessionmaker_of(DB_URL)() as session:
        session.add(Jurisdiction(
            id=jurisdiction_id, name=f"Test {jurisdiction_id}", state="Delhi",
            path=f"test_{jurisdiction_id.hex}"))
        session.add(User(
            id=officer_id, full_name="Integration Officer",
            email=f"officer-{officer_id}@example.test", role="FIELD_OFFICER",
            jurisdiction_id=jurisdiction_id))
        session.commit()
    return create_app(Settings(
        db_url=DB_URL, officer_uuid=str(officer_id), jurisdiction_uuid=str(jurisdiction_id),
        storage_root=str(tmp_path_factory.mktemp("db-evidence"))))


@pytest.fixture(scope="module")
def auth_app(tmp_path_factory):
    jurisdiction_id, reviewer_id, auditor_id, admin_id = (
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    reviewer_password = "reviewer-local-password-2026"
    auditor_password = "auditor-local-password-2026"
    admin_password = "administrator-local-password-2026"
    with sessionmaker_of(DB_URL)() as session:
        session.add(Jurisdiction(
            id=jurisdiction_id, name=f"Auth {jurisdiction_id}", state="Delhi",
            path=f"auth_{jurisdiction_id.hex}"))
        session.add_all([
            User(id=reviewer_id, full_name="Integration Reviewer",
                 email=f"reviewer-{reviewer_id}@example.test", role="REVIEWING_OFFICER",
                 jurisdiction_id=jurisdiction_id, password_hash=hash_password(reviewer_password)),
            User(id=auditor_id, full_name="Integration Auditor",
                 email=f"auditor-{auditor_id}@example.test", role="AUDITOR",
                 jurisdiction_id=jurisdiction_id, password_hash=hash_password(auditor_password)),
            User(id=admin_id, full_name="Integration Administrator",
                 email=f"admin-{admin_id}@example.test", role="ADMIN",
                 jurisdiction_id=jurisdiction_id, password_hash=hash_password(admin_password)),
        ])
        session.commit()
    app = create_app(Settings(
        db_url=DB_URL, officer_uuid=str(reviewer_id),
        jurisdiction_uuid=str(jurisdiction_id), auth_mode="local",
        jwt_key_path=str(tmp_path_factory.mktemp("auth-key") / "jwt.pem"),
        storage_root=str(tmp_path_factory.mktemp("auth-evidence")),
        allow_self_review=True))
    return app, {
        "reviewer_email": f"reviewer-{reviewer_id}@example.test",
        "reviewer_password": reviewer_password,
        "auditor_email": f"auditor-{auditor_id}@example.test",
        "auditor_password": auditor_password,
        "admin_email": f"admin-{admin_id}@example.test",
        "admin_password": admin_password,
    }


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "white").save(output, "JPEG")
    return output.getvalue()


async def _request(app, method: str, path: str, **kwargs):
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def test_postgres_round_trip_keeps_images_evaluations_and_reports(database_app):
    raw = _jpeg()
    digest = hashlib.sha256(raw).hexdigest()
    client_uuid = str(uuid.uuid4())
    data = {
        "client_uuid": client_uuid, "captured_at": "2026-09-07",
        "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
        "coverage_asserted": "false", "panels": ["FRONT"],
        "image_sha256": [digest],
    }
    files = [("images", ("front.jpg", raw, "image/jpeg"))]
    created = await _request(
        database_app, "POST", "/api/v1/scans", data=data, files=files)
    duplicate = await _request(
        database_app, "POST", "/api/v1/scans", data=data, files=files)
    assert created.status_code == 202 and duplicate.status_code == 200
    assert created.json()["scan_id"] == duplicate.json()["scan_id"]

    def reader(_data, *, panel, **_kwargs):
        return [Token("MRP Rs. 45.00 (incl. of all taxes)", 1, 2, 300, 20,
                      conf=0.99, panel=panel)]

    database_app.state.pipeline.reader = reader
    scan_id = created.json()["scan_id"]
    evaluated = await _request(
        database_app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    assert evaluated.status_code == 202
    assert len(evaluated.json()["evaluations"]) == 21
    assert evaluated.json()["images"][0]["max_edge_used"] == 32

    report = await _request(database_app, "POST", f"/api/v1/scans/{scan_id}/report")
    assert report.status_code == 201
    reports = await _request(
        database_app, "GET", f"/api/v1/scans/{scan_id}/reports")
    assert reports.status_code == 200
    assert reports.json()["items"][0]["id"] == report.json()["report_id"]
    downloaded = await _request(
        database_app, "GET",
        f"/api/v1/reports/{report.json()['report_id']}/download?format=pdf")
    assert downloaded.content.startswith(b"%PDF-")


async def test_postgres_round_trip_keeps_ecommerce_listing_evidence(database_app):
    raw = _jpeg()
    digest = hashlib.sha256(raw).hexdigest()
    listing_text = "MRP Rs. 45.00 (incl. of all taxes)\nNet Qty 500 g"
    created = await _request(
        database_app, "POST", "/api/v1/scans",
        data={
            "client_uuid": str(uuid.uuid4()), "captured_at": "2026-09-10",
            "mode": "ECOMMERCE_LISTING", "category": "FOOD",
            "coverage_asserted": "false", "panels": ["LISTING", "LISTING_2"],
            "image_sha256": [digest, digest],
            "ecommerce": json.dumps({
                "url": "https://shop.example.test/products/45",
                "listing_text": listing_text,
            }),
        },
        files=[("images", ("listing-1.jpg", raw, "image/jpeg")),
               ("images", ("listing-2.jpg", raw, "image/jpeg"))])
    assert created.status_code == 202

    scan_id = created.json()["scan_id"]
    fetched = await _request(database_app, "GET", f"/api/v1/scans/{scan_id}")
    assert fetched.status_code == 200
    assert fetched.json()["mode"] == "ECOMMERCE_LISTING"
    assert fetched.json()["coverage_asserted"] is False
    assert fetched.json()["ecommerce"] == {
        "url": "https://shop.example.test/products/45",
        "listing_text": listing_text,
    }
    assert fetched.json()["panels_captured"] == ["LISTING", "LISTING_2"]


async def test_local_login_rotation_and_rbac_are_enforced(auth_app):
    app, credentials = auth_app
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        anonymous = await client.get(
            "/api/v1/scans/00000000-0000-4000-8000-000000000000")
        bad = await client.post("/api/v1/auth/login", json={
            "email": credentials["reviewer_email"], "password": "incorrect-password"})
        login = await client.post("/api/v1/auth/login", json={
            "email": credentials["reviewer_email"].upper(),
            "password": credentials["reviewer_password"]})
        assert anonymous.status_code == 401 and bad.status_code == 401
        assert login.status_code == 200 and "HttpOnly" in login.headers["set-cookie"]
        assert login.headers["cache-control"] == "no-store"
        first_refresh = login.json()["refresh_token"]
        access = login.json()["access_token"]
        me = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
        rotated = await client.post("/api/v1/auth/refresh")
        replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": first_refresh})
        family = await client.post("/api/v1/auth/refresh")
        assert me.json()["role"] == "REVIEWING_OFFICER"
        assert rotated.status_code == 200
        assert rotated.json()["refresh_token"] != first_refresh
        assert replay.status_code == family.status_code == 401

        auditor = await client.post("/api/v1/auth/login", json={
            "email": credentials["auditor_email"],
            "password": credentials["auditor_password"]})
        auditor_access = auditor.json()["access_token"]
        raw = _jpeg()
        denied = await client.post(
            "/api/v1/scans",
            headers={"Authorization": f"Bearer {auditor_access}"},
            data={
                "client_uuid": str(uuid.uuid4()), "captured_at": "2026-09-07",
                "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
                "coverage_asserted": "false", "panels": ["FRONT"],
                "image_sha256": [hashlib.sha256(raw).hexdigest()],
            }, files=[("images", ("front.jpg", raw, "image/jpeg"))])
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "E_FORBIDDEN"


async def test_admin_manages_account_and_one_use_mobile_enrollment(auth_app):
    app, credentials = auth_app
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/v1/auth/login", json={
            "email": credentials["admin_email"],
            "password": credentials["admin_password"]})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        jurisdictions = await client.get("/api/v1/admin/jurisdictions", headers=headers)
        jurisdiction_id = jurisdictions.json()["items"][0]["id"]
        created = await client.post("/api/v1/admin/users", headers=headers, json={
            "full_name": "Mobile Field Officer", "email": f"mobile-{uuid.uuid4()}@example.test",
            "role": "FIELD_OFFICER", "jurisdiction_id": jurisdiction_id})
        assert created.status_code == 201
        invitation = await client.post(
            f"/api/v1/admin/users/{created.json()['id']}/enrollments",
            headers=headers, json={"server_url": "http://192.168.1.20:8000"})
        body = invitation.json()
        assert invitation.status_code == 201
        assert body["enrollment_uri"].startswith("lmpc://enroll?")
        assert body["server_fingerprint"] == app.state.auth.server_fingerprint()

        enrolled = await client.post("/api/v1/auth/enroll", json={
            "token": body["token"], "device_name": "Integration Android"})
        replay = await client.post("/api/v1/auth/enroll", json={
            "token": body["token"], "device_name": "Replay"})
        assert enrolled.status_code == 200
        assert enrolled.json()["user"]["role"] == "FIELD_OFFICER"
        assert replay.status_code == 401

        field_headers = {
            "Authorization": f"Bearer {enrolled.json()['access_token']}"}
        raw = _jpeg()
        field_scan = await client.post(
            "/api/v1/scans", headers=field_headers,
            data={"client_uuid": str(uuid.uuid4()), "captured_at": "2026-09-10",
                  "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
                  "buyer_type": "RETAIL", "coverage_asserted": "true",
                  "panels": ["FRONT", "BACK"],
                  "image_sha256": [hashlib.sha256(raw).hexdigest()] * 2},
            files=[("images", ("front.jpg", raw, "image/jpeg")),
                   ("images", ("back.jpg", raw, "image/jpeg"))])
        assert field_scan.status_code == 202

        def reader(_data, *, panel, **_kwargs):
            return [Token("MRP Rs. 45.00 (incl. of all taxes)", 1, 2, 300, 20,
                          conf=0.99, panel=panel)]

        app.state.pipeline.reader = reader
        scan_id = field_scan.json()["scan_id"]
        processed = await client.post(
            f"/api/v1/scans/{scan_id}/process", headers=field_headers)
        repeated = await client.post(
            f"/api/v1/scans/{scan_id}/process", headers=field_headers)
        forbidden = await client.post(
            f"/api/v1/scans/{scan_id}/reevaluate", headers=field_headers)
        assert processed.status_code == 202
        assert len(processed.json()["evaluations"]) == 21
        assert repeated.status_code == 409
        assert forbidden.status_code == 403

        users = await client.get("/api/v1/admin/users", headers=headers)
        assert created.json()["id"] in {item["id"] for item in users.json()["items"]}


async def test_postgres_review_rows_are_scoped_append_only_and_audited(auth_app):
    app, credentials = auth_app
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/v1/auth/login", json={
            "email": credentials["reviewer_email"],
            "password": credentials["reviewer_password"]})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        raw = _jpeg()
        created = await client.post(
            "/api/v1/scans", headers=headers,
            data={"client_uuid": str(uuid.uuid4()), "captured_at": "2026-09-07",
                  "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
                  "coverage_asserted": "true", "panels": ["FRONT", "BACK"],
                  "image_sha256": [hashlib.sha256(raw).hexdigest()] * 2},
            files=[("images", ("front.jpg", raw, "image/jpeg")),
                   ("images", ("back.jpg", raw, "image/jpeg"))])
        scan_id = created.json()["scan_id"]

        def reader(_data, *, panel, **_kwargs):
            return [Token("MRP Rs. 45.00 (incl. of all taxes)", 1, 2, 300, 20,
                          conf=0.99, panel=panel)]

        app.state.pipeline.reader = reader
        first = await client.post(
            f"/api/v1/scans/{scan_id}/reevaluate", headers=headers)
        listing = await client.get(
            "/api/v1/scans?category=FOOD&page_size=100", headers=headers)
        dashboard = await client.get("/api/v1/dashboard/summary", headers=headers)
        outside = await client.get(
            f"/api/v1/scans?jurisdiction_id={uuid.uuid4()}", headers=headers)
        assert first.status_code == 202 and listing.status_code == dashboard.status_code == 200
        assert scan_id in {row["id"] for row in listing.json()["items"]}
        assert dashboard.json()["total"] == 1
        assert outside.status_code == 403

        correction = await client.post(
            f"/api/v1/scans/{scan_id}/declarations/mrp", headers=headers,
            json={"text": "MRP Rs. 52.00 (incl. of all taxes)",
                  "bbox": [4, 5, 310, 22]})
        assert correction.status_code == 200
        second = await client.post(
            f"/api/v1/scans/{scan_id}/reevaluate", headers=headers)
        corrected = next(item for item in second.json()["declarations"]
                         if item["field"] == "mrp")
        assert corrected["text"].startswith("MRP Rs. 52.00")
        assert corrected["corrected_by"] is not None

        target = next(item for item in second.json()["evaluations"]
                      if item["outcome"] == "FAIL")
        override = await client.post(
            f"/api/v1/scans/{scan_id}/evaluations/{target['id']}/override",
            headers=headers,
            json={"outcome": "PASS",
                  "reason": "Declaration was verified against the physical label"})
        history = await client.get(
            f"/api/v1/scans/{scan_id}/evaluations?batch=2", headers=headers)
        quality = await client.get("/api/v1/dashboard/quality", headers=headers)
        assert override.status_code == 200 and history.status_code == 200
        assert len(history.json()["evaluations"]) == 22
        assert len(history.json()["effective"]) == 21
        assert quality.json()["false_accusation_guard_breaches"] == 0
        report = await client.post(f"/api/v1/scans/{scan_id}/report", headers=headers)
        assert report.status_code == 201

    with app.state.scan_store.sessions() as session:
        scan_uuid = uuid.UUID(scan_id)
        assert session.scalar(select(func.count()).select_from(
            ExtractedDeclaration).where(
                ExtractedDeclaration.scan_id == scan_uuid,
                ExtractedDeclaration.corrected_by.is_not(None))) >= 2
        assert session.scalar(select(func.count()).select_from(RuleEvaluation).where(
            RuleEvaluation.scan_id == scan_uuid,
            RuleEvaluation.check_code == target["check"])) == 3
        actions = set(session.scalars(select(AuditLog.action).where(
            AuditLog.entity_id.in_([uuid.UUID(correction.json()["declaration"]["id"]),
                                    uuid.UUID(override.json()["evaluation"]["id"]),
                                    uuid.UUID(report.json()["report_id"])]))))
        assert actions == {"DECLARATION_CORRECT", "EVALUATION_OVERRIDE",
                           "REPORT_FINALIZE"}
        stored_report = session.get(ComplianceReport, uuid.UUID(report.json()["report_id"]))
        assert str(stored_report.reviewed_by) == override.json()["evaluation"]["overridden_by"]
