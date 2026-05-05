from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from myorch.app import create_app
from myorch.services.session_manager import SessionManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    apps = tmp_path / "APPS"
    apps.mkdir()
    (apps / "gate").mkdir()
    (apps / "gate" / "manage.py").write_text("# stub")
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    monkeypatch.setenv("MYORCH_APPS_ROOT", str(apps))
    app = create_app()
    app.state.session_mgr = SessionManager(
        memory=app.state.memory, settings=app.state.settings,
        claude_argv_factory=lambda **kw: ["cat"],
    )
    return TestClient(app)


def test_workspace_html_fragment(client: TestClient):
    client.post("/projects/scan")
    r = client.get("/sessions/workspace/gate")
    assert r.status_code == 200
    assert "terminal" in r.text.lower()


def test_open_session_returns_session_id(client: TestClient):
    client.post("/projects/scan")
    r = client.post("/sessions/open", json={"project": "gate"})
    assert r.status_code == 200
    assert "session_id" in r.json()


def test_websocket_echoes_input_to_pty(client: TestClient):
    client.post("/projects/scan")
    sid = client.post("/sessions/open", json={"project": "gate"}).json()["session_id"]
    with client.websocket_connect(f"/sessions/ws/{sid}") as ws:
        ws.send_text("hello\n")
        chunks = ""
        for _ in range(20):
            try:
                chunks += ws.receive_text()
            except Exception:
                break
            if "hello" in chunks:
                break
        assert "hello" in chunks
