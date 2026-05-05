from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from myorch.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    monkeypatch.setenv("MYORCH_APPS_ROOT", str(tmp_path / "APPS"))
    (tmp_path / "APPS").mkdir()
    return TestClient(create_app())


def test_home_returns_200(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "MyOrchestrator" in r.text


def test_health_endpoint(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
