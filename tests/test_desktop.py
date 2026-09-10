"""Portable-launcher paths and safety defaults."""
from __future__ import annotations

import os

from lmpc import desktop


def test_desktop_environment_is_local_and_s3_free(tmp_path, monkeypatch):
    monkeypatch.setenv("LMPC_DESKTOP_DATA_DIR", str(tmp_path / "portable"))
    monkeypatch.setenv("LMPC_DB_URL", "postgresql://must-not-be-used")
    monkeypatch.setenv("LMPC_S3_BUCKET", "must-not-be-used")

    data_root = desktop._configure_environment()

    assert data_root == (tmp_path / "portable").resolve()
    assert os.environ["LMPC_DB_URL"] == ""
    assert os.environ["LMPC_S3_BUCKET"] == ""
    assert os.environ["LMPC_AUTH_MODE"] == "disabled"
    assert os.environ["LMPC_STORAGE_ROOT"] == str(data_root / "objects")
    assert os.environ["LMPC_RULEPACK_PATH"].endswith("rulepack/current.json")


def test_desktop_rejects_invalid_port():
    assert desktop.main(["--port", "0", "--no-browser"]) == 2
