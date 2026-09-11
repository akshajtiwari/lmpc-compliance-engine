"""Executable role-by-endpoint matrix for every protected API route."""
from __future__ import annotations

import hashlib
import io
import uuid

import httpx
import pytest
from fastapi.routing import APIRoute
from PIL import Image

from lmpc.engine.model import Token
from lmpc.server.config import Settings
from lmpc.server.main import create_app
from lmpc.server.svc.auth_core import Principal, ROLE_PERMISSIONS

pytestmark = pytest.mark.anyio

ENDPOINT_PERMISSIONS = {
    ("GET", "/admin/users"): "users:read",
    ("POST", "/admin/users"): "users:manage",
    ("PATCH", "/admin/users/{user_id}"): "users:manage",
    ("GET", "/admin/jurisdictions"): "users:read",
    ("POST", "/admin/users/{user_id}/enrollments"): "users:manage",
    ("POST", "/scans"): "scans:create",
    ("POST", "/scans/deferred"): "scans:create",
    ("POST", "/scans/{scan_id}/images"): "scans:create",
    ("POST", "/scans/{scan_id}/complete-upload"): "scans:create",
    ("GET", "/scans"): "scans:read",
    ("GET", "/scans/{scan_id}"): "scans:read",
    ("GET", "/scans/{scan_id}/images/{panel}"): "scans:read",
    ("POST", "/scans/{scan_id}/reevaluate"): "scans:reevaluate",
    ("POST", "/scans/{scan_id}/process"): "scans:create",
    ("PATCH", "/scans/{scan_id}"): "scans:update",
    ("POST", "/scans/{scan_id}/declarations/{field}"): "declarations:correct",
    ("GET", "/scans/{scan_id}/evaluations"): "evaluations:read",
    ("POST", "/scans/{scan_id}/evaluations/{evaluation_id}/override"):
        "evaluations:override",
    ("GET", "/scans/{scan_id}/reports"): "reports:read",
    ("POST", "/scans/{scan_id}/report"): "reports:create",
    ("GET", "/reports/{report_id}"): "reports:read",
    ("GET", "/reports/{report_id}/download"): "reports:export",
    ("GET", "/dashboard/summary"): "dashboard:read",
    ("GET", "/dashboard/violations-by-type"): "dashboard:read",
    ("GET", "/dashboard/top-non-compliant"): "dashboard:read",
    ("GET", "/dashboard/geo"): "dashboard:read",
    ("GET", "/dashboard/quality"): "dashboard:read",
    ("GET", "/rules/{check_code}"): "rules:read",
}
ROLE_NEUTRAL_ENDPOINTS = {
    ("POST", "/auth/login"), ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"), ("GET", "/auth/me"),
    ("POST", "/auth/enroll"), ("GET", "/healthz"),
    ("GET", "/readyz"), ("GET", "/version"), ("GET", "/metrics"),
}


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


class _Accounts:
    def list_users(self, _principal):
        return []

    def create_user(self, values, _principal):
        return {"id": str(uuid.uuid4()), **values}

    def update_user(self, user_id, values, _principal):
        return {"id": user_id, **values}

    def list_jurisdictions(self):
        return []

    def issue_enrollment(self, user_id, server_url, _principal):
        return {"user_id": user_id, "server_url": server_url, "token": "test-token"}


def _permission(route: APIRoute) -> str | None:
    found: list[str] = []

    def visit(dependencies) -> None:
        for dependency in dependencies:
            permission = getattr(dependency.call, "required_permission", None)
            if permission:
                found.append(permission)
            visit(dependency.dependencies)

    visit(route.dependant.dependencies)
    assert len(found) <= 1, f"{route.path} has multiple role permissions: {found}"
    return found[0] if found else None


def test_every_api_route_is_role_neutral_or_has_one_matrix_permission(tmp_path):
    app = create_app(Settings(storage_root=str(tmp_path)))
    protected = {}
    role_neutral = set()
    for route in _api_routes(app.routes):
        permission = _permission(route)
        for method in route.methods:
            key = (method, route.path)
            if permission:
                protected[key] = permission
            else:
                role_neutral.add(key)
    assert protected == ENDPOINT_PERMISSIONS
    assert role_neutral == ROLE_NEUTRAL_ENDPOINTS


def _api_routes(routes):
    """Traverse FastAPI 0.135's lazy included-router wrappers."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _api_routes(original.routes)


@pytest.mark.parametrize("role", ROLE_PERMISSIONS)
async def test_every_role_attempts_every_protected_endpoint(role, tmp_path):
    app = create_app(Settings(storage_root=str(tmp_path), allow_self_review=True))
    app.state.accounts = _Accounts()
    seeded = await _seed(app)
    principal = Principal(
        id=str(uuid.uuid4()), full_name=f"{role} matrix actor",
        email=f"{role.casefold()}@matrix.test", role=role,
        jurisdiction_id=str(uuid.uuid4()), is_legal_reviewer=role == "ADMIN",
        permissions=frozenset(ROLE_PERMISSIONS[role]))
    app.state.auth.current = lambda _token: principal

    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer matrix-role"}) as client:
        for method, route, path, success, kwargs in _cases(seeded):
            response = await client.request(method, path, **kwargs)
            permission = ENDPOINT_PERMISSIONS[(method, route)]
            expected = success if permission in principal.permissions else 403
            assert response.status_code == expected, (
                f"{role} {method} {route} requires {permission}: "
                f"expected {expected}, got {response.status_code} {response.text[:300]}")


async def _seed(app) -> dict:
    def reader(_data, *, panel, **_kwargs):
        return [Token("MRP Rs. 45.00 (incl. of all taxes)", 1, 2, 300, 20,
                      conf=0.99, panel=panel)]

    app.state.pipeline.reader = reader
    review = await _new_scan(app)
    review = await _request(app, "POST", f"/api/v1/scans/{review['scan_id']}/reevaluate")
    report_scan = await _new_scan(app)
    report_scan = await _request(
        app, "POST", f"/api/v1/scans/{report_scan['scan_id']}/reevaluate")
    report = await _request(
        app, "POST", f"/api/v1/scans/{report_scan['scan_id']}/report")
    finalize = await _new_scan(app)
    finalize = await _request(
        app, "POST", f"/api/v1/scans/{finalize['scan_id']}/reevaluate")
    received = await _new_scan(app)
    return {
        "review": review, "report_scan": report_scan,
        "report": report, "finalize": finalize, "received": received,
    }


async def _new_scan(app) -> dict:
    raw = _jpeg()
    digest = hashlib.sha256(raw).hexdigest()
    return await _request(app, "POST", "/api/v1/scans", data={
        "client_uuid": str(uuid.uuid4()), "captured_at": "2026-09-11",
        "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
        "coverage_asserted": "true", "panels": ["FRONT", "BACK"],
        "image_sha256": [digest, digest],
    }, files=[("images", ("front.jpg", raw, "image/jpeg")),
              ("images", ("back.jpg", raw, "image/jpeg"))])


async def _request(app, method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, path, **kwargs)
    assert response.status_code in {200, 201, 202, 204}, response.text
    return response.json() if response.content else {}


def _cases(seeded: dict) -> list[tuple[str, str, str, int, dict]]:
    review = seeded["review"]
    scan_id = review["scan_id"]
    evaluation = review["evaluations"][0]
    report_scan_id = seeded["report_scan"]["scan_id"]
    report_id = seeded["report"]["report_id"]
    raw = _jpeg()
    digest = hashlib.sha256(raw).hexdigest()
    user_id = str(uuid.uuid4())
    account = {
        "full_name": "Matrix user", "email": f"{uuid.uuid4()}@matrix.test",
        "role": "FIELD_OFFICER", "jurisdiction_id": None,
    }
    return [
        ("GET", "/admin/users", "/api/v1/admin/users", 200, {}),
        ("POST", "/admin/users", "/api/v1/admin/users", 201, {"json": account}),
        ("PATCH", "/admin/users/{user_id}", f"/api/v1/admin/users/{user_id}",
         200, {"json": {"full_name": "Updated matrix user"}}),
        ("GET", "/admin/jurisdictions", "/api/v1/admin/jurisdictions", 200, {}),
        ("POST", "/admin/users/{user_id}/enrollments",
         f"/api/v1/admin/users/{user_id}/enrollments", 201,
         {"json": {"server_url": "http://192.168.1.20:8000"}}),
        ("POST", "/scans", "/api/v1/scans", 202, {
            "data": {"client_uuid": str(uuid.uuid4()), "captured_at": "2026-09-11",
                     "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
                     "coverage_asserted": "false", "panels": ["FRONT"],
                     "image_sha256": [digest]},
            "files": [("images", ("front.jpg", raw, "image/jpeg"))],
        }),
        ("GET", "/scans", "/api/v1/scans", 200, {}),
        ("GET", "/scans/{scan_id}", f"/api/v1/scans/{scan_id}", 200, {}),
        ("GET", "/scans/{scan_id}/images/{panel}",
         f"/api/v1/scans/{scan_id}/images/FRONT", 200, {}),
        ("POST", "/scans/{scan_id}/declarations/{field}",
         f"/api/v1/scans/{scan_id}/declarations/mrp", 200,
         {"json": {"text": "MRP Rs. 49.00 (incl. of all taxes)"}}),
        ("GET", "/scans/{scan_id}/evaluations",
         f"/api/v1/scans/{scan_id}/evaluations", 200, {}),
        ("POST", "/scans/{scan_id}/evaluations/{evaluation_id}/override",
         f"/api/v1/scans/{scan_id}/evaluations/{evaluation['id']}/override", 200,
         {"json": {"outcome": "PASS", "reason": "Matrix-authorised review"}}),
        ("POST", "/scans/{scan_id}/reevaluate",
         f"/api/v1/scans/{scan_id}/reevaluate", 202, {}),
        ("PATCH", "/scans/{scan_id}", f"/api/v1/scans/{scan_id}", 200,
         {"json": {"package_shape": "CYLINDRICAL"}}),
        ("POST", "/scans/{scan_id}/process",
         f"/api/v1/scans/{seeded['received']['scan_id']}/process", 202, {}),
        ("GET", "/scans/{scan_id}/reports",
         f"/api/v1/scans/{report_scan_id}/reports", 200, {}),
        ("GET", "/reports/{report_id}", f"/api/v1/reports/{report_id}", 200, {}),
        ("GET", "/reports/{report_id}/download",
         f"/api/v1/reports/{report_id}/download?format=pdf", 200, {}),
        ("POST", "/scans/{scan_id}/report",
         f"/api/v1/scans/{seeded['finalize']['scan_id']}/report", 201, {}),
        ("GET", "/dashboard/summary", "/api/v1/dashboard/summary", 200, {}),
        ("GET", "/dashboard/violations-by-type",
         "/api/v1/dashboard/violations-by-type", 200, {}),
        ("GET", "/dashboard/top-non-compliant",
         "/api/v1/dashboard/top-non-compliant", 200, {}),
        ("GET", "/dashboard/geo", "/api/v1/dashboard/geo", 200, {}),
        ("GET", "/dashboard/quality", "/api/v1/dashboard/quality", 200, {}),
        ("GET", "/rules/{check_code}",
         f"/api/v1/rules/{evaluation['check']}", 200, {}),
    ]


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "white").save(output, "JPEG")
    return output.getvalue()
