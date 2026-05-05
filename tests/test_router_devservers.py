import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from myorch.app import create_app
from myorch.models import Project


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    monkeypatch.setenv("MYORCH_APPS_ROOT", str(tmp_path / "APPS"))
    (tmp_path / "APPS").mkdir()
    app = create_app()
    p = app.state.memory.upsert_project(Project(
        name="alpha", path=str(tmp_path),
        dev_command="echo started && sleep 30",
    ))
    return TestClient(app)


def test_start_endpoint(client: TestClient):
    r = client.post("/devservers/alpha/start")
    assert r.status_code == 200
    deadline = time.time() + 3.0
    while time.time() < deadline:
        tail = client.get("/devservers/alpha/tail").json()["lines"]
        if any("started" in line for line in tail):
            break
        time.sleep(0.05)
    client.post("/devservers/alpha/stop")


def test_status_reflects_running(client: TestClient):
    client.post("/devservers/alpha/start")
    r = client.get("/devservers/alpha/status")
    assert r.json()["running"] is True
    client.post("/devservers/alpha/stop")
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not client.get("/devservers/alpha/status").json()["running"]:
            break
        time.sleep(0.05)
    assert not client.get("/devservers/alpha/status").json()["running"]


def test_tail_html_escapes_output(client: TestClient):
    """If the dev server prints HTML, the tail HTML response must escape it."""
    p = client.app.state.memory.get_project_by_name("alpha")
    client.app.state.memory.update_project(p.id, dev_command='echo "<script>x</script>"')
    client.post("/devservers/alpha/start")
    deadline = time.time() + 3.0
    while time.time() < deadline:
        r = client.get("/devservers/alpha/tail",
                       headers={"hx-request": "true", "accept": "text/html"})
        if "script" in r.text:
            break
        time.sleep(0.1)
    client.post("/devservers/alpha/stop")
    assert "<script>" not in r.text
    assert "&lt;script&gt;" in r.text
