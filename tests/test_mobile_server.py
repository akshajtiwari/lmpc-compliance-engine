"""Mobile/LAN boundary tests that do not require PostgreSQL."""
from __future__ import annotations

import pytest

from lmpc.server.api.errors import ApiError
from lmpc.server.svc.accounts import _server_url


@pytest.mark.parametrize("value, expected", [
    ("http://192.168.1.20:8000/", "http://192.168.1.20:8000"),
    ("https://lmpc.department.test/path", "https://lmpc.department.test"),
])
def test_enrollment_server_url_is_reduced_to_an_origin(value, expected):
    assert _server_url(value) == expected


@pytest.mark.parametrize("value", [
    "", "ftp://192.168.1.20", "http:///missing-host",
    "http://user@192.168.1.20", "http://:password@192.168.1.20",
])
def test_invalid_enrollment_server_url_is_refused(value):
    with pytest.raises(ApiError):
        _server_url(value)
