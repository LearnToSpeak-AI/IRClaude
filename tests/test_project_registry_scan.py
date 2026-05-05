from pathlib import Path

import pytest

from myorch.db import connect, init_schema
from myorch.services.memory_service import MemoryService
from myorch.services.project_registry import ProjectRegistry


@pytest.fixture
def setup(tmp_path: Path) -> tuple[ProjectRegistry, MemoryService, Path]:
    apps = tmp_path / "APPS"
    apps.mkdir()
    (apps / "gate").mkdir()
    (apps / "gate" / "manage.py").write_text("# stub")
    (apps / "front").mkdir()
    (apps / "front" / "package.json").write_text("{}")
    (apps / ".hidden").mkdir()  # should be skipped
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    memory = MemoryService(conn)
    return ProjectRegistry(memory, apps), memory, apps


def test_scan_discovers_visible_directories(setup):
    reg, _, _ = setup
    out = reg.scan()
    assert {p.name for p in out} == {"gate", "front"}


def test_scan_persists_projects(setup):
    reg, memory, _ = setup
    reg.scan()
    assert memory.get_project_by_name("gate") is not None
    assert memory.get_project_by_name("front") is not None


def test_scan_does_not_overwrite_user_edits(setup):
    reg, memory, _ = setup
    reg.scan()
    p = memory.get_project_by_name("gate")
    memory.update_project(p.id, dev_command="my custom cmd")
    reg.scan()
    p2 = memory.get_project_by_name("gate")
    assert p2.dev_command == "my custom cmd"


def test_scan_with_missing_apps_root_returns_empty(tmp_path: Path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    reg = ProjectRegistry(MemoryService(conn), tmp_path / "does_not_exist")
    assert reg.scan() == []
