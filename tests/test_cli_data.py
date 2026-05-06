from pathlib import Path

from typer.testing import CliRunner

from irclaude.cli import app
from irclaude.db import connect, init_schema
from irclaude.models import Decision, Project, Recall
from irclaude.services.memory_service import MemoryService


runner = CliRunner()


def _seed(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "d"; data.mkdir()
    monkeypatch.setenv("IRCLAUDE_DATA_DIR", str(data))
    monkeypatch.setenv("IRCLAUDE_APPS_ROOT", str(tmp_path / "apps"))
    conn = connect(data / "data.db"); init_schema(conn)
    mem = MemoryService(conn)
    proj = mem.upsert_project(Project(name="Speaking MCP", path=str(tmp_path / "apps" / "speakingmcp")))
    (tmp_path / "apps" / "speakingmcp").mkdir(parents=True)
    mem.save_recall(proj.id, Recall(project_id=proj.id, text="websockets need keepalive", tags=["infra"]))
    mem.save_decision(
        proj.id,
        Decision(project_id=proj.id, title="use UTC", body="all timestamps stored UTC"),
    )


def test_list_shows_known_projects(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Speaking MCP" in result.stdout


def test_search_finds_recall_text(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    result = runner.invoke(app, ["search", "keepalive"])
    assert result.exit_code == 0
    assert "keepalive" in result.stdout.lower()


def test_decisions_lists_for_project(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    result = runner.invoke(app, ["decisions", "Speaking MCP"])
    assert result.exit_code == 0
    assert "use UTC" in result.stdout


def test_decisions_unknown_project_returns_nonzero(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    result = runner.invoke(app, ["decisions", "Nope"])
    assert result.exit_code != 0


def test_scan_imports_new_dirs(monkeypatch, tmp_path):
    data = tmp_path / "d"; data.mkdir()
    apps = tmp_path / "apps"; (apps / "foo").mkdir(parents=True)
    monkeypatch.setenv("IRCLAUDE_DATA_DIR", str(data))
    monkeypatch.setenv("IRCLAUDE_APPS_ROOT", str(apps))
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0
    assert "foo" in result.stdout.lower() or "1" in result.stdout
