from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from myorch.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    apps = tmp_path / "APPS"
    apps.mkdir()
    (apps / "gate").mkdir()
    (apps / "gate" / "manage.py").write_text("# stub")
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    monkeypatch.setenv("MYORCH_APPS_ROOT", str(apps))
    return TestClient(create_app())


def test_scan_creates_projects(client: TestClient):
    r = client.post("/projects/scan")
    assert r.status_code == 200
    assert "gate" in r.text


def test_list_returns_html_fragment(client: TestClient):
    client.post("/projects/scan")
    r = client.get("/projects")
    assert r.status_code == 200
    assert "gate" in r.text


def test_update_project_dev_command(client: TestClient):
    client.post("/projects/scan")
    r = client.patch("/projects/gate", data={"dev_command": "custom run"})
    assert r.status_code == 200
    body = r.json()
    assert body["dev_command"] == "custom run"
