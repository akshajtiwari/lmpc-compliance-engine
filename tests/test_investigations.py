"""Investigations: the folder an officer creates, fills, and reopens later.

The scan used to be the only unit of work, so an officer came back to a flat list of
inspections with no way to say which belonged to which sweep. These tests pin the folder,
its idempotent creation over a flaky link, and — the part that is easy to get wrong — who
is allowed to open somebody else's.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from lmpc.server.config import Settings
from lmpc.server.db import desktop_bootstrap, sessionmaker_of
from lmpc.server.db.investigations import Investigation
from lmpc.server.db.models import Jurisdiction, User
from lmpc.server.main import create_app
from lmpc.server.svc.auth_core import Principal, ROLE_PERMISSIONS

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _principal(role: str, user_id: str, jurisdiction_id: str | None) -> Principal:
    return Principal(id=user_id, full_name=f"Test {role}", email=f"{role}@local",
                     role=role, jurisdiction_id=jurisdiction_id,
                     is_legal_reviewer=False,
                     permissions=frozenset(ROLE_PERMISSIONS[role]))


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """A real database with two jurisdictions, so scoping can actually be tested."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    db_url = f"sqlite+pysqlite:///{data_root / 'lmpc.sqlite3'}"
    monkeypatch.setenv("LMPC_JWT_KEY_PATH", str(data_root / "jwt.pem"))
    record = desktop_bootstrap.run(data_root, db_url)

    sessions = sessionmaker_of(db_url)
    with sessions() as session:
        far = Jurisdiction(name="Elsewhere", state="Other", path="elsewhere")
        session.add(far)
        session.flush()
        stranger = User(full_name="Other Officer", email="other@lmpc.local",
                        role="FIELD_OFFICER", jurisdiction_id=far.id)
        colleague = User(full_name="Colleague", email="colleague@lmpc.local",
                         role="FIELD_OFFICER",
                         jurisdiction_id=uuid.UUID(record["jurisdiction_id"]))
        session.add_all([stranger, colleague])
        session.commit()
        ids = (str(stranger.id), str(colleague.id), str(far.id))

    app = create_app(Settings(
        db_url=db_url, auth_mode="local", storage_root=str(data_root / "objects"),
        jwt_key_path=str(data_root / "jwt.pem"),
        officer_uuid=record["officer"]["id"],
        jurisdiction_uuid=record["jurisdiction_id"]))
    app.state.db_url = db_url
    return {
        "app": app, "sessions": sessions,
        "home": record["jurisdiction_id"], "away": ids[2],
        "officer": _principal("FIELD_OFFICER", record["officer"]["id"],
                              record["jurisdiction_id"]),
        "colleague": _principal("FIELD_OFFICER", ids[1], record["jurisdiction_id"]),
        "stranger": _principal("FIELD_OFFICER", ids[0], ids[2]),
        "admin": _principal("ADMIN", record["admin"]["id"],
                            record["jurisdiction_id"]),
    }


def client(app, principal) -> httpx.AsyncClient:
    app.dependency_overrides = {}
    from lmpc.server.api.auth import current_principal
    app.dependency_overrides[current_principal] = lambda: principal
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                             base_url="http://testserver")


async def _create(app, principal, **values):
    body = {"name": "Britannia sweep", **values}
    async with client(app, principal) as http:
        return await http.post("/investigations", json=body)


async def test_an_officer_opens_a_folder_and_finds_it_again(world):
    made = await _create(world["app"], world["officer"],
                         subject_brand="Britannia", location_text="Sector 14 market",
                         investigation_type="RETAIL_SWEEP")
    assert made.status_code == 201, made.text
    folder = made.json()
    assert folder["status"] == "OPEN"
    assert folder["name"] == "Britannia sweep"

    async with client(world["app"], world["officer"]) as http:
        again = await http.get(f"/investigations/{folder['id']}")
        assert again.status_code == 200
        assert again.json()["subject_brand"] == "Britannia"
        listed = await http.get("/investigations")
        assert [row["id"] for row in listed.json()["items"]] == [folder["id"]]


async def test_a_retried_create_returns_the_same_folder(world):
    """The phone creates a folder with no signal and retries for an hour. Without
    idempotency the officer comes back online to five copies of one investigation."""
    client_uuid = str(uuid.uuid4())
    first = await _create(world["app"], world["officer"], client_uuid=client_uuid)
    second = await _create(world["app"], world["officer"], client_uuid=client_uuid)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate_ignored"] is True
    assert second.json()["id"] == first.json()["id"]

    with world["sessions"]() as session:
        assert len(session.scalars(select(Investigation)).all()) == 1


async def test_a_colleague_in_the_same_jurisdiction_can_open_the_folder(world):
    """An investigation is a shared case file. Two officers working the same market must
    both be able to add to it — this is deliberately wider than the own-scans-only rule
    a field officer has over individual scans."""
    folder = (await _create(world["app"], world["officer"])).json()
    async with client(world["app"], world["colleague"]) as http:
        assert (await http.get(f"/investigations/{folder['id']}")).status_code == 200
        assert (await http.get("/investigations")).json()["total"] == 1


async def test_another_jurisdiction_cannot_see_it_at_all(world):
    folder = (await _create(world["app"], world["officer"])).json()
    async with client(world["app"], world["stranger"]) as http:
        missing = await http.get(f"/investigations/{folder['id']}")
        # 404, not 403: a "forbidden" would confirm the folder exists.
        assert missing.status_code == 404
        assert (await http.get("/investigations")).json()["total"] == 0


async def test_search_and_filter_narrow_the_list(world):
    app = world["app"]
    await _create(app, world["officer"], name="Britannia sweep",
                  subject_brand="Britannia", investigation_type="RETAIL_SWEEP")
    await _create(app, world["officer"], name="Amul audit", subject_brand="Amul",
                  investigation_type="MANUFACTURER_AUDIT")
    async with client(app, world["officer"]) as http:
        assert (await http.get("/investigations", params={"q": "amul"})).json()["total"] == 1
        by_type = await http.get("/investigations",
                                 params={"investigation_type": "RETAIL_SWEEP"})
        assert [r["name"] for r in by_type.json()["items"]] == ["Britannia sweep"]
        by_name = await http.get("/investigations", params={"sort": "name"})
        assert [r["name"] for r in by_name.json()["items"]] == \
            ["Amul audit", "Britannia sweep"]


async def test_closing_a_folder_records_when_and_refuses_new_scans(world):
    folder = (await _create(world["app"], world["officer"])).json()
    async with client(world["app"], world["officer"]) as http:
        closed = await http.patch(f"/investigations/{folder['id']}",
                                  json={"status": "CLOSED"})
        assert closed.status_code == 200
        assert closed.json()["status"] == "CLOSED"
        assert closed.json()["closed_at"] is not None

    service = world["app"].state.investigations
    with pytest.raises(Exception) as refused:
        service.ensure_open(world["officer"], folder["id"])
    assert "closed" in str(refused.value)


async def test_notes_are_append_only_and_keep_their_author(world):
    """An editable notes blob would destroy the attribution trail: a report that quotes a
    note has to be able to say who wrote it and when."""
    folder = (await _create(world["app"], world["officer"])).json()
    async with client(world["app"], world["officer"]) as http:
        first = await http.post(f"/investigations/{folder['id']}/notes",
                                json={"body": "Shopkeeper produced no invoice."})
        assert first.status_code == 201
    async with client(world["app"], world["colleague"]) as http:
        await http.post(f"/investigations/{folder['id']}/notes",
                        json={"body": "Second visit, same shelf."})
        listed = (await http.get(f"/investigations/{folder['id']}/notes")).json()["items"]

    assert len(listed) == 2
    assert {note["author"] for note in listed} == {"Field Officer", "Colleague"}
    assert listed[0]["body"] == "Second visit, same shelf."      # newest first


async def test_stats_start_empty_and_are_derived_not_counted(world):
    folder = (await _create(world["app"], world["officer"])).json()
    async with client(world["app"], world["officer"]) as http:
        stats = (await http.get(f"/investigations/{folder['id']}/stats")).json()
    assert stats == {"investigation_id": folder["id"], "scan_count": 0,
                     "evaluated_count": 0, "pending_count": 0,
                     "by_overall": {}, "top_violations": []}


async def test_a_folder_rejects_an_unknown_type(world):
    async with client(world["app"], world["officer"]) as http:
        bad = await http.post("/investigations",
                              json={"name": "x", "investigation_type": "NONSENSE"})
        assert bad.status_code == 422 or bad.json()["error"]["code"] == "E_VALIDATION"


async def test_an_unnamed_folder_is_refused(world):
    async with client(world["app"], world["officer"]) as http:
        assert (await http.post("/investigations", json={"name": "   "})).status_code \
            in (400, 422)
