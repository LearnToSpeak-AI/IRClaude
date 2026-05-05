from datetime import datetime

from myorch.models import Project, Session, Decision, Recall, SessionStatus


def test_project_minimum_required():
    p = Project(name="alpha", path="/tmp/alpha")
    assert p.name == "alpha"
    assert p.dev_port is None
    assert p.metadata == {}


def test_project_full_round_trip():
    data = {
        "id": 1, "name": "gate", "path": "/tmp/gate", "type": "django",
        "dev_command": "python manage.py runserver", "dev_port": 8000,
        "description": "auth service", "last_session_id": "abc-123",
        "created_at": datetime(2026, 1, 1), "last_opened_at": None,
        "metadata": {"missing": False},
    }
    p = Project(**data)
    assert p.dev_port == 8000


def test_session_status_enum():
    s = Session(project_id=1, status=SessionStatus.active)
    assert s.status == SessionStatus.active
    assert s.status.value == "active"


def test_decision_requires_title_and_body():
    d = Decision(project_id=1, title="Use JWT", body="Reasoning here")
    assert d.tags == []


def test_recall_requires_text():
    r = Recall(project_id=1, text="endpoint needs header X")
    assert r.tags == []
