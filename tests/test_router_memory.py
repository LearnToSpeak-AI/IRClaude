from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from myorch.app import create_app
from myorch.models import Decision, Project, Recall


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    monkeypatch.setenv("MYORCH_APPS_ROOT", str(tmp_path / "APPS"))
    (tmp_path / "APPS").mkdir()
    app = create_app()
    p = app.state.memory.upsert_project(Project(name="alpha", path="/tmp/alpha"))
    app.state.memory.save_decision(p.id, Decision(project_id=p.id, title="JWT", body="auth"))
    app.state.memory.save_recall(p.id, Recall(project_id=p.id, text="X-Forwarded-For"))
    return TestClient(app)


def test_decisions_list(client: TestClient):
    r = client.get("/memory/alpha/decisions")
    assert r.status_code == 200
    assert "JWT" in r.text


def test_recalls_list(client: TestClient):
    r = client.get("/memory/alpha/recalls")
    assert r.status_code == 200
    assert "X-Forwarded-For" in r.text


def test_html_is_escaped_against_xss(client: TestClient):
    """Saved content with HTML tags must be escaped in the rendered fragment."""
    p = client.app.state.memory.get_project_by_name("alpha")
    client.app.state.memory.save_decision(
        p.id,
        Decision(project_id=p.id, title="<script>alert(1)</script>",
                 body="<img src=x onerror=alert(1)>"),
    )
    r = client.get("/memory/alpha/decisions")
    assert "<script>" not in r.text  # raw tag must NOT appear
    assert "&lt;script&gt;" in r.text or "&amp;lt;script&amp;gt;" in r.text


def test_search(client: TestClient):
    r = client.get("/memory/alpha/search", params={"q": "JWT"})
    assert r.status_code == 200
    body = r.json()
    assert any("JWT" in (h.get("snippet") or "") for h in body["hits"])


def test_create_decision(client: TestClient):
    r = client.post("/memory/alpha/decisions",
                    data={"title": "Postgres", "body": "not sqlite"})
    assert r.status_code == 200
    r2 = client.get("/memory/alpha/decisions")
    assert "Postgres" in r2.text


def test_create_recall(client: TestClient):
    r = client.post("/memory/alpha/recalls", data={"text": "port 8000"})
    assert r.status_code == 200
    r2 = client.get("/memory/alpha/recalls")
    assert "port 8000" in r2.text
