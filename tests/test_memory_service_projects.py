from pathlib import Path

import pytest

from irclaude.db import connect, init_schema
from irclaude.models import Project
from irclaude.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> MemoryService:
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    return MemoryService(conn)


def test_upsert_creates_new_project(memory: MemoryService):
    p = memory.upsert_project(Project(name="alpha", path="/tmp/alpha", type="python"))
    assert p.id is not None
    assert p.name == "alpha"


def test_upsert_does_not_overwrite_dev_command(memory: MemoryService):
    p1 = memory.upsert_project(Project(name="alpha", path="/tmp/alpha", dev_command="cmd-a"))
    memory.update_project(p1.id, dev_command="cmd-b-user-edit")
    p2 = memory.upsert_project(Project(name="alpha", path="/tmp/alpha", dev_command="cmd-a-rescanned"))
    assert p2.dev_command == "cmd-b-user-edit"


def test_list_projects_returns_all(memory: MemoryService):
    memory.upsert_project(Project(name="a", path="/tmp/a"))
    memory.upsert_project(Project(name="b", path="/tmp/b"))
    out = memory.list_projects()
    assert {p.name for p in out} == {"a", "b"}


def test_get_project_by_name(memory: MemoryService):
    memory.upsert_project(Project(name="gate", path="/tmp/gate"))
    p = memory.get_project_by_name("gate")
    assert p is not None and p.path == "/tmp/gate"
    assert memory.get_project_by_name("nope") is None
