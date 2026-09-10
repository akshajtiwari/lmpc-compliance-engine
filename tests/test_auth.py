"""Local identity primitives and the complete role/permission matrix."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lmpc.server.db.models import User
from lmpc.server.svc.auth import ALL_PERMISSIONS, ROLE_PERMISSIONS, _record_failure
from lmpc.server.svc.auth_core import hash_password


EXPECTED = {
    "FIELD_OFFICER": {
        "scans:create", "scans:read", "scans:update", "declarations:correct",
        "evaluations:read", "reports:read", "reports:export", "products:read",
        "dashboard:read",
    },
    "REVIEWING_OFFICER": {
        "scans:create", "scans:read", "scans:update", "scans:reevaluate",
        "declarations:correct", "evaluations:read", "evaluations:override",
        "reports:create", "reports:read", "reports:export", "products:read",
        "products:merge", "rules:read", "dashboard:read",
    },
    "ADMIN": {
        "scans:create", "scans:read", "scans:update", "scans:reevaluate",
        "declarations:correct", "evaluations:read", "evaluations:override",
        "reports:create", "reports:read", "reports:export", "products:read",
        "products:merge", "rules:read", "rules:approve", "users:read", "users:manage",
        "jurisdictions:manage", "dashboard:read", "dashboard:read_all", "audit:read",
    },
    "AUDITOR": {
        "scans:read", "evaluations:read", "reports:read", "reports:export",
        "products:read", "rules:read", "users:read", "dashboard:read", "audit:read",
    },
}


def test_role_permission_matrix_is_exact():
    assert ROLE_PERMISSIONS == EXPECTED
    assert ALL_PERMISSIONS == frozenset().union(*EXPECTED.values())


def test_local_passwords_use_the_required_argon2id_cost():
    encoded = hash_password("a-correct-horse-battery-staple")
    assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")


@pytest.mark.parametrize("password", ["short", "password1234", "123456789012"])
def test_short_or_common_local_passwords_are_refused(password):
    with pytest.raises(ValueError):
        hash_password(password)


def test_five_failures_inside_fifteen_minutes_lock_for_fifteen_minutes():
    user = User(full_name="Test", email="test@example.test", role="FIELD_OFFICER")
    start = datetime(2026, 9, 10, tzinfo=UTC)
    for minute in range(5):
        _record_failure(user, start + timedelta(minutes=minute))
    assert user.failed_login_count == 5
    assert user.locked_until == start + timedelta(minutes=19)
