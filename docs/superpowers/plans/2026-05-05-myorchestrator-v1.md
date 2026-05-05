# MyOrchestrator V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web orchestrator (FastAPI + HTMX + xterm.js + SQLite) that lets the user manage Claude Code sessions across all projects under `<APPS_ROOT>/*` from a single browser pane, with persistent cross-session memory injected into Claude via a local MCP server.

**Architecture:** Launcher pattern — one Claude Code subprocess per project (PTY-managed via pexpect), shared SQLite memory accessed both by the FastAPI backend and a separate MCP server stdio process spawned by `claude`. No `ANTHROPIC_API_KEY`: subprocess invocation only, leveraging the user's Pro/Max subscription.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX, Alpine.js, Tailwind (CDN), xterm.js, pexpect, sqlite3 (stdlib, WAL + FTS5), pydantic v2, pytest.

**Reference:** See `docs/superpowers/specs/2026-05-05-myorchestrator-design.md` for the full design rationale.

**Security note:** All HTML rendering uses Jinja2 templates with auto-escaping enabled (default). Never build HTML strings via Python f-strings with user/DB content; always go through `templates.TemplateResponse(...)` so Jinja escapes interpolated values. The terminal panel uses xterm.js's `term.write()` (safe) — never `innerHTML` with untrusted content.

---

## Milestone 0 — Project bootstrap

**Goal:** Empty but well-tooled Python project with git, venv, pyproject, tests passing on a smoke test.

### Task 0.1: Initialize git and pyproject

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Modify: existing `main.py` will be deleted (it's the PyCharm placeholder)

- [ ] **Step 1: Initialize git**

```bash
cd <APPS_ROOT>/MyOrchestrator
git init
git branch -M main
```

Expected: `Initialized empty Git repository in .../MyOrchestrator/.git/`

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
.idea/
.coverage
htmlcov/
*.db
*.db-journal
*.db-wal
*.db-shm
/tmp/
node_modules/
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "myorch"
version = "0.1.0"
description = "Local orchestrator for multi-project Claude Code sessions"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "jinja2>=3.1",
  "pydantic>=2.6",
  "pexpect>=4.9",
  "python-multipart>=0.0.9",
  "mcp>=1.0",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "httpx>=0.27",
  "ruff>=0.4",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["myorch*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- [ ] **Step 4: Delete placeholder, create package skeleton**

```bash
rm main.py
mkdir -p myorch tests
touch myorch/__init__.py tests/__init__.py
```

- [ ] **Step 5: Set up venv and install**

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Expected: Successful install of all dependencies.

- [ ] **Step 6: Smoke test**

```bash
pytest --collect-only
```

Expected: `no tests ran in 0.00s` (no tests yet, but pytest works).

- [ ] **Step 7: Commit**

```bash
git add .gitignore pyproject.toml myorch/__init__.py tests/__init__.py
git commit -m "chore: bootstrap python project with fastapi + pytest"
```

---

### Task 0.2: Config module

**Files:**
- Create: `myorch/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path

from myorch.config import Settings


def test_default_settings_resolve_paths():
    s = Settings()
    assert s.apps_root == Path("<APPS_ROOT>")
    assert s.data_dir.name == ".myorch"
    assert s.db_path.suffix == ".db"
    assert s.tmp_dir == Path("/tmp/myorch")
    assert s.host == "127.0.0.1"
    assert s.port == 7000


def test_settings_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("MYORCH_PORT", "9999")
    monkeypatch.setenv("MYORCH_APPS_ROOT", "/tmp/fake_apps")
    s = Settings()
    assert s.port == 9999
    assert s.apps_root == Path("/tmp/fake_apps")
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'myorch.config'`.

- [ ] **Step 3: Implement `myorch/config.py`**

```python
import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    apps_root: Path = Field(default_factory=lambda: Path(os.environ.get(
        "MYORCH_APPS_ROOT", "<APPS_ROOT>"
    )))
    data_dir: Path = Field(default_factory=lambda: Path(os.environ.get(
        "MYORCH_DATA_DIR", str(Path.home() / ".myorch")
    )))
    tmp_dir: Path = Field(default_factory=lambda: Path(os.environ.get(
        "MYORCH_TMP_DIR", "/tmp/myorch"
    )))
    host: str = Field(default_factory=lambda: os.environ.get("MYORCH_HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.environ.get("MYORCH_PORT", "7000")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data.db"

    @property
    def mcp_config_path(self) -> Path:
        return self.data_dir / "mcp.json"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/config.py tests/test_config.py
git commit -m "feat: add Settings config with env overrides"
```

---

## Milestone 1 — Database layer

**Goal:** SQLite schema, migrations, connection management, FTS5 triggers — fully tested.

### Task 1.1: Database connection helper

**Files:**
- Create: `myorch/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
import sqlite3
from pathlib import Path

import pytest

from myorch.db import connect, init_schema


def test_connect_creates_file_and_enables_wal(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    assert db_path.exists()
    cur = conn.execute("PRAGMA journal_mode")
    assert cur.fetchone()[0] == "wal"
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()


def test_init_schema_creates_all_tables(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    init_schema(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    expected = {
        "projects", "sessions", "decisions", "recalls",
        "global_preferences", "memory_fts",
    }
    assert expected.issubset(names)
    conn.close()


def test_init_schema_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    init_schema(conn)
    init_schema(conn)  # should not raise
    conn.close()
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `myorch/db.py`**

```python
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    path            TEXT NOT NULL UNIQUE,
    type            TEXT,
    dev_command     TEXT,
    dev_port        INTEGER,
    description     TEXT,
    last_session_id TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_opened_at  TIMESTAMP,
    metadata        TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    claude_session_id   TEXT,
    started_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at            TIMESTAMP,
    summary             TEXT,
    files_touched       TEXT,
    status              TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at DESC);

CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_id  INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    tags        TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS recalls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    tags        TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_recalls_project ON recalls(project_id);

CREATE TABLE IF NOT EXISTS global_preferences (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    key   TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    note  TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,
    project_id UNINDEXED,
    origin UNINDEXED,
    tokenize = 'porter unicode61'
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
```

- [ ] **Step 4: Run tests (pass)**

Run: `pytest tests/test_db.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/db.py tests/test_db.py
git commit -m "feat: add sqlite connection helper with WAL + schema init"
```

---

### Task 1.2: FTS5 sync triggers

**Files:**
- Modify: `myorch/db.py` (extend SCHEMA with triggers)
- Test: `tests/test_db_fts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_fts.py
from pathlib import Path

from myorch.db import connect, init_schema


def _setup(tmp_path: Path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    conn.execute(
        "INSERT INTO projects(name, path) VALUES (?, ?)",
        ("alpha", "/tmp/alpha"),
    )
    return conn


def test_decision_insert_appears_in_fts(tmp_path: Path):
    conn = _setup(tmp_path)
    conn.execute(
        "INSERT INTO decisions(project_id, title, body) VALUES (1, ?, ?)",
        ("Use JWT", "Decided JWT for auth via simplejwt"),
    )
    rows = conn.execute(
        "SELECT origin FROM memory_fts WHERE memory_fts MATCH 'JWT'"
    ).fetchall()
    origins = {r["origin"] for r in rows}
    assert "decision:1" in origins


def test_recall_insert_appears_in_fts(tmp_path: Path):
    conn = _setup(tmp_path)
    conn.execute(
        "INSERT INTO recalls(project_id, text) VALUES (1, ?)",
        ("Endpoint requires X-Forwarded-For",),
    )
    rows = conn.execute(
        "SELECT origin FROM memory_fts WHERE memory_fts MATCH 'X-Forwarded-For'"
    ).fetchall()
    assert {r["origin"] for r in rows} == {"recall:1"}


def test_session_summary_update_appears_in_fts(tmp_path: Path):
    conn = _setup(tmp_path)
    conn.execute("INSERT INTO sessions(project_id) VALUES (1)")
    conn.execute(
        "UPDATE sessions SET summary=? WHERE id=1",
        ("Worked on refresh tokens rotation",),
    )
    rows = conn.execute(
        "SELECT origin FROM memory_fts WHERE memory_fts MATCH 'rotation'"
    ).fetchall()
    assert {r["origin"] for r in rows} == {"session:1"}


def test_decision_delete_removes_from_fts(tmp_path: Path):
    conn = _setup(tmp_path)
    conn.execute(
        "INSERT INTO decisions(project_id, title, body) VALUES (1, ?, ?)",
        ("Use JWT", "Decided JWT"),
    )
    conn.execute("DELETE FROM decisions WHERE id=1")
    rows = conn.execute(
        "SELECT origin FROM memory_fts WHERE memory_fts MATCH 'JWT'"
    ).fetchall()
    assert rows == []
```

- [ ] **Step 2: Run tests (fail)**

Run: `pytest tests/test_db_fts.py -v`
Expected: FAIL — FTS rows are empty (no triggers yet).

- [ ] **Step 3: Add triggers to SCHEMA in `myorch/db.py`**

Append to the `SCHEMA` constant in `myorch/db.py`:

```python
SCHEMA += """
CREATE TRIGGER IF NOT EXISTS trg_decisions_ai AFTER INSERT ON decisions BEGIN
    INSERT INTO memory_fts(rowid, content, project_id, origin)
    VALUES (NULL, NEW.title || ' ' || NEW.body, NEW.project_id, 'decision:' || NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_decisions_ad AFTER DELETE ON decisions BEGIN
    DELETE FROM memory_fts WHERE origin = 'decision:' || OLD.id;
END;
CREATE TRIGGER IF NOT EXISTS trg_decisions_au AFTER UPDATE ON decisions BEGIN
    DELETE FROM memory_fts WHERE origin = 'decision:' || OLD.id;
    INSERT INTO memory_fts(rowid, content, project_id, origin)
    VALUES (NULL, NEW.title || ' ' || NEW.body, NEW.project_id, 'decision:' || NEW.id);
END;

CREATE TRIGGER IF NOT EXISTS trg_recalls_ai AFTER INSERT ON recalls BEGIN
    INSERT INTO memory_fts(rowid, content, project_id, origin)
    VALUES (NULL, NEW.text, NEW.project_id, 'recall:' || NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_recalls_ad AFTER DELETE ON recalls BEGIN
    DELETE FROM memory_fts WHERE origin = 'recall:' || OLD.id;
END;
CREATE TRIGGER IF NOT EXISTS trg_recalls_au AFTER UPDATE ON recalls BEGIN
    DELETE FROM memory_fts WHERE origin = 'recall:' || OLD.id;
    INSERT INTO memory_fts(rowid, content, project_id, origin)
    VALUES (NULL, NEW.text, NEW.project_id, 'recall:' || NEW.id);
END;

CREATE TRIGGER IF NOT EXISTS trg_sessions_au_summary AFTER UPDATE OF summary ON sessions
WHEN NEW.summary IS NOT NULL AND NEW.summary != '' BEGIN
    DELETE FROM memory_fts WHERE origin = 'session:' || OLD.id;
    INSERT INTO memory_fts(rowid, content, project_id, origin)
    VALUES (NULL, NEW.summary, NEW.project_id, 'session:' || NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_sessions_ad AFTER DELETE ON sessions BEGIN
    DELETE FROM memory_fts WHERE origin = 'session:' || OLD.id;
END;
"""
```

- [ ] **Step 4: Run tests (pass)**

Run: `pytest tests/test_db_fts.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/db.py tests/test_db_fts.py
git commit -m "feat: add FTS5 sync triggers for decisions, recalls, sessions"
```

---

### Task 1.3: Pydantic models

**Files:**
- Create: `myorch/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
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
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `myorch/models.py`**

```python
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    active = "active"
    closed = "closed"
    crashed = "crashed"


class Project(BaseModel):
    id: int | None = None
    name: str
    path: str
    type: str | None = None
    dev_command: str | None = None
    dev_port: int | None = None
    description: str | None = None
    last_session_id: str | None = None
    created_at: datetime | None = None
    last_opened_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    id: int | None = None
    project_id: int
    claude_session_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: str | None = None
    files_touched: list[str] = Field(default_factory=list)
    status: SessionStatus = SessionStatus.active


class Decision(BaseModel):
    id: int | None = None
    project_id: int
    session_id: int | None = None
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class Recall(BaseModel):
    id: int | None = None
    project_id: int
    text: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class GlobalPreference(BaseModel):
    id: int | None = None
    key: str
    value: str
    note: str | None = None


class SessionBrief(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime | None
    summary: str | None
    status: SessionStatus


class RecallHit(BaseModel):
    origin: str
    score: float
    snippet: str
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/models.py tests/test_models.py
git commit -m "feat: add pydantic models for projects, sessions, memory"
```

---

## Milestone 2 — Memory Service

**Goal:** Single class that owns all SQLite I/O for memory: CRUD, FTS search, digest generation. Tested in isolation.

### Task 2.1: MemoryService — projects CRUD

**Files:**
- Create: `myorch/services/__init__.py` (empty)
- Create: `myorch/services/memory_service.py`
- Test: `tests/test_memory_service_projects.py`

- [ ] **Step 1: Create services package**

```bash
mkdir -p myorch/services
touch myorch/services/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_memory_service_projects.py
from pathlib import Path

import pytest

from myorch.db import connect, init_schema
from myorch.models import Project
from myorch.services.memory_service import MemoryService


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
```

- [ ] **Step 3: Run test (fails)**

Run: `pytest tests/test_memory_service_projects.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `myorch/services/memory_service.py`**

```python
import json
import sqlite3
from typing import Any

from myorch.models import Project


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"], name=row["name"], path=row["path"], type=row["type"],
        dev_command=row["dev_command"], dev_port=row["dev_port"],
        description=row["description"], last_session_id=row["last_session_id"],
        created_at=row["created_at"], last_opened_at=row["last_opened_at"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
    )


class MemoryService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---- projects ----
    def upsert_project(self, p: Project) -> Project:
        existing = self.get_project_by_name(p.name)
        if existing:
            return existing  # do NOT overwrite — respects user edits
        cur = self.conn.execute(
            """INSERT INTO projects(name, path, type, dev_command, dev_port,
                                    description, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (p.name, p.path, p.type, p.dev_command, p.dev_port, p.description,
             json.dumps(p.metadata) if p.metadata else None),
        )
        return self.get_project_by_id(cur.lastrowid)  # type: ignore[arg-type]

    def update_project(self, project_id: int, **fields: Any) -> Project:
        if not fields:
            return self.get_project_by_id(project_id)  # type: ignore[return-value]
        if "metadata" in fields and isinstance(fields["metadata"], dict):
            fields["metadata"] = json.dumps(fields["metadata"])
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(
            f"UPDATE projects SET {cols} WHERE id=?",
            (*fields.values(), project_id),
        )
        return self.get_project_by_id(project_id)  # type: ignore[return-value]

    def get_project_by_id(self, project_id: int) -> Project | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        return _row_to_project(row) if row else None

    def get_project_by_name(self, name: str) -> Project | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name=?", (name,)
        ).fetchone()
        return _row_to_project(row) if row else None

    def list_projects(self) -> list[Project]:
        rows = self.conn.execute(
            "SELECT * FROM projects ORDER BY name"
        ).fetchall()
        return [_row_to_project(r) for r in rows]
```

- [ ] **Step 5: Run test (passes)**

Run: `pytest tests/test_memory_service_projects.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add myorch/services/__init__.py myorch/services/memory_service.py tests/test_memory_service_projects.py
git commit -m "feat: add MemoryService with project CRUD (upsert respects user edits)"
```

---

### Task 2.2: MemoryService — sessions CRUD

**Files:**
- Modify: `myorch/services/memory_service.py`
- Test: `tests/test_memory_service_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_service_sessions.py
import json
from pathlib import Path

import pytest

from myorch.db import connect, init_schema
from myorch.models import Project, SessionStatus
from myorch.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> tuple[MemoryService, int]:
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="alpha", path="/tmp/alpha"))
    assert p.id
    return m, p.id


def test_start_session_creates_active_row(memory):
    m, pid = memory
    s = m.start_session(pid)
    assert s.id is not None
    assert s.status == SessionStatus.active
    assert s.project_id == pid


def test_set_claude_session_id_persists_and_updates_project(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.set_claude_session_id(s.id, "claude-uuid-abc")  # type: ignore[arg-type]
    s2 = m.get_session(s.id)  # type: ignore[arg-type]
    assert s2.claude_session_id == "claude-uuid-abc"
    p = m.get_project_by_id(pid)
    assert p.last_session_id == "claude-uuid-abc"


def test_save_summary_writes_summary_and_files(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.save_summary(s.id, "did stuff", ["a.py", "b.py"])  # type: ignore[arg-type]
    s2 = m.get_session(s.id)  # type: ignore[arg-type]
    assert s2.summary == "did stuff"
    assert s2.files_touched == ["a.py", "b.py"]


def test_close_session_sets_status_and_ended_at(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.close_session(s.id, status=SessionStatus.closed)  # type: ignore[arg-type]
    s2 = m.get_session(s.id)  # type: ignore[arg-type]
    assert s2.status == SessionStatus.closed
    assert s2.ended_at is not None


def test_list_recent_sessions_orders_desc(memory):
    m, pid = memory
    s1 = m.start_session(pid)
    s2 = m.start_session(pid)
    out = m.list_recent_sessions(pid, limit=10)
    assert out[0].id == s2.id
    assert out[1].id == s1.id
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_memory_service_sessions.py -v`
Expected: FAIL — methods missing.

- [ ] **Step 3: Add session methods to `MemoryService` in `myorch/services/memory_service.py`**

Add imports at top:

```python
from datetime import datetime, timezone

from myorch.models import Session, SessionBrief, SessionStatus
```

Add methods to the class:

```python
    # ---- sessions ----
    def start_session(self, project_id: int) -> Session:
        cur = self.conn.execute(
            "INSERT INTO sessions(project_id) VALUES (?)", (project_id,)
        )
        return self.get_session(cur.lastrowid)  # type: ignore[return-value]

    def get_session(self, session_id: int) -> Session | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return Session(
            id=row["id"], project_id=row["project_id"],
            claude_session_id=row["claude_session_id"],
            started_at=row["started_at"], ended_at=row["ended_at"],
            summary=row["summary"],
            files_touched=json.loads(row["files_touched"]) if row["files_touched"] else [],
            status=SessionStatus(row["status"]),
        )

    def set_claude_session_id(self, session_id: int, claude_id: str) -> None:
        self.conn.execute(
            "UPDATE sessions SET claude_session_id=? WHERE id=?",
            (claude_id, session_id),
        )
        # mirror onto project so we can --resume next time
        self.conn.execute(
            """UPDATE projects SET last_session_id=?
               WHERE id=(SELECT project_id FROM sessions WHERE id=?)""",
            (claude_id, session_id),
        )

    def save_summary(self, session_id: int, summary: str,
                     files_touched: list[str] | None = None) -> None:
        self.conn.execute(
            "UPDATE sessions SET summary=?, files_touched=? WHERE id=?",
            (summary, json.dumps(files_touched or []), session_id),
        )

    def close_session(self, session_id: int, status: SessionStatus = SessionStatus.closed) -> None:
        self.conn.execute(
            "UPDATE sessions SET status=?, ended_at=? WHERE id=?",
            (status.value, datetime.now(timezone.utc).isoformat(), session_id),
        )

    def list_recent_sessions(self, project_id: int, limit: int = 5) -> list[SessionBrief]:
        rows = self.conn.execute(
            """SELECT id, started_at, ended_at, summary, status FROM sessions
               WHERE project_id=? ORDER BY started_at DESC LIMIT ?""",
            (project_id, limit),
        ).fetchall()
        return [
            SessionBrief(
                id=r["id"], started_at=r["started_at"], ended_at=r["ended_at"],
                summary=r["summary"], status=SessionStatus(r["status"]),
            )
            for r in rows
        ]
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_memory_service_sessions.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/memory_service.py tests/test_memory_service_sessions.py
git commit -m "feat: add session CRUD to MemoryService with claude_session_id mirroring"
```

---

### Task 2.3: MemoryService — decisions, recalls, FTS search

**Files:**
- Modify: `myorch/services/memory_service.py`
- Test: `tests/test_memory_service_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_service_memory.py
from pathlib import Path

import pytest

from myorch.db import connect, init_schema
from myorch.models import Decision, Project, Recall
from myorch.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> tuple[MemoryService, int]:
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="alpha", path="/tmp/alpha"))
    return m, p.id  # type: ignore[return-value]


def test_save_decision_returns_id(memory):
    m, pid = memory
    d = m.save_decision(pid, Decision(project_id=pid, title="JWT", body="auth"))
    assert d.id is not None


def test_list_decisions_filters_by_tag(memory):
    m, pid = memory
    m.save_decision(pid, Decision(project_id=pid, title="A", body="x", tags=["auth"]))
    m.save_decision(pid, Decision(project_id=pid, title="B", body="y", tags=["db"]))
    auth = m.list_decisions(pid, tag="auth")
    assert len(auth) == 1 and auth[0].title == "A"
    all_ = m.list_decisions(pid, tag=None)
    assert len(all_) == 2


def test_save_recall_persists(memory):
    m, pid = memory
    r = m.save_recall(pid, Recall(project_id=pid, text="X-Forwarded-For required"))
    assert r.id is not None


def test_recall_search_finds_decisions_recalls_and_summaries(memory):
    m, pid = memory
    m.save_decision(pid, Decision(project_id=pid, title="JWT", body="auth via simplejwt"))
    m.save_recall(pid, Recall(project_id=pid, text="endpoint X needs JWT"))
    s = m.start_session(pid)
    m.save_summary(s.id, "Implemented JWT login")  # type: ignore[arg-type]
    hits = m.recall(pid, "JWT", limit=10)
    origins = {h.origin for h in hits}
    assert "decision:1" in origins
    assert "recall:1" in origins
    assert "session:1" in origins


def test_recall_does_not_leak_other_projects(memory):
    m, pid = memory
    p2 = m.upsert_project(Project(name="beta", path="/tmp/beta"))
    m.save_decision(pid, Decision(project_id=pid, title="JWT alpha", body="alpha-only"))
    m.save_decision(p2.id, Decision(project_id=p2.id, title="JWT beta", body="beta-only"))  # type: ignore[arg-type]
    hits = m.recall(pid, "JWT")
    assert len(hits) == 1
    assert "alpha-only" in hits[0].snippet or "JWT alpha" in hits[0].snippet
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_memory_service_memory.py -v`
Expected: FAIL — methods missing.

- [ ] **Step 3: Add methods to `MemoryService`**

Update imports at the top of `memory_service.py`:

```python
from myorch.models import Decision, Recall, RecallHit
```

Add methods:

```python
    # ---- decisions ----
    def save_decision(self, project_id: int, d: Decision) -> Decision:
        cur = self.conn.execute(
            """INSERT INTO decisions(project_id, session_id, title, body, tags)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, d.session_id, d.title, d.body,
             json.dumps(d.tags) if d.tags else None),
        )
        row = self.conn.execute(
            "SELECT * FROM decisions WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return Decision(
            id=row["id"], project_id=row["project_id"], session_id=row["session_id"],
            title=row["title"], body=row["body"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            created_at=row["created_at"],
        )

    def list_decisions(self, project_id: int, tag: str | None = None) -> list[Decision]:
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        out = [
            Decision(
                id=r["id"], project_id=r["project_id"], session_id=r["session_id"],
                title=r["title"], body=r["body"],
                tags=json.loads(r["tags"]) if r["tags"] else [],
                created_at=r["created_at"],
            )
            for r in rows
        ]
        if tag is not None:
            out = [d for d in out if tag in d.tags]
        return out

    # ---- recalls ----
    def save_recall(self, project_id: int, r: Recall) -> Recall:
        cur = self.conn.execute(
            "INSERT INTO recalls(project_id, text, tags) VALUES (?, ?, ?)",
            (project_id, r.text, json.dumps(r.tags) if r.tags else None),
        )
        row = self.conn.execute(
            "SELECT * FROM recalls WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return Recall(
            id=row["id"], project_id=row["project_id"], text=row["text"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            created_at=row["created_at"],
        )

    def list_recalls(self, project_id: int) -> list[Recall]:
        rows = self.conn.execute(
            "SELECT * FROM recalls WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [
            Recall(
                id=r["id"], project_id=r["project_id"], text=r["text"],
                tags=json.loads(r["tags"]) if r["tags"] else [],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ---- search ----
    def recall(self, project_id: int, query: str, limit: int = 10) -> list[RecallHit]:
        rows = self.conn.execute(
            """SELECT origin, snippet(memory_fts, 0, '<<', '>>', '...', 16) AS snip,
                      bm25(memory_fts) AS score
               FROM memory_fts
               WHERE memory_fts MATCH ? AND project_id = ?
               ORDER BY score LIMIT ?""",
            (query, project_id, limit),
        ).fetchall()
        return [
            RecallHit(origin=r["origin"], score=float(r["score"]), snippet=r["snip"])
            for r in rows
        ]
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_memory_service_memory.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/memory_service.py tests/test_memory_service_memory.py
git commit -m "feat: add decisions, recalls, and FTS5 recall to MemoryService"
```

---

### Task 2.4: Digest generator

**Files:**
- Create: `myorch/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_digest.py
from pathlib import Path

import pytest

from myorch.db import connect, init_schema
from myorch.digest import generate_digest
from myorch.models import Decision, Project, Recall
from myorch.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path: Path) -> tuple[MemoryService, int]:
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="gate", path="/tmp/gate"))
    return m, p.id  # type: ignore[return-value]


def test_digest_for_empty_project_says_no_history(memory):
    m, pid = memory
    text = generate_digest(m, pid)
    assert "Sin historial" in text or "no history" in text.lower()


def test_digest_includes_last_session_summary(memory):
    m, pid = memory
    s = m.start_session(pid)
    m.save_summary(s.id, "Implemented refresh tokens", ["auth.py"])  # type: ignore[arg-type]
    text = generate_digest(m, pid)
    assert "refresh tokens" in text


def test_digest_includes_decisions_and_recalls(memory):
    m, pid = memory
    m.save_decision(pid, Decision(project_id=pid, title="JWT auth", body="via simplejwt"))
    m.save_recall(pid, Recall(project_id=pid, text="endpoint X needs token"))
    text = generate_digest(m, pid)
    assert "JWT auth" in text
    assert "endpoint X needs token" in text


def test_digest_under_token_budget(memory):
    m, pid = memory
    for i in range(50):
        m.save_decision(pid, Decision(project_id=pid, title=f"D{i}", body="x" * 200))
    text = generate_digest(m, pid)
    # rough heuristic: keep under ~600 tokens ~= 2400 chars
    assert len(text) < 4000
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_digest.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `myorch/digest.py`**

```python
from myorch.services.memory_service import MemoryService

MAX_DECISIONS = 5
MAX_RECALLS = 5


def generate_digest(memory: MemoryService, project_id: int) -> str:
    project = memory.get_project_by_id(project_id)
    if project is None:
        return "[Sin proyecto]"

    sessions = memory.list_recent_sessions(project_id, limit=1)
    decisions = memory.list_decisions(project_id)[:MAX_DECISIONS]
    recalls = memory.list_recalls(project_id)[:MAX_RECALLS]

    if not sessions and not decisions and not recalls:
        return (
            f"[Contexto del proyecto: {project.name}]\n"
            f"Sin historial todavía. La memoria crecerá conforme trabajes."
        )

    lines = [f"[Contexto del proyecto: {project.name}]"]

    if sessions and sessions[0].summary:
        lines.append("")
        lines.append(f"Última sesión ({sessions[0].started_at}):")
        lines.append(f"  {sessions[0].summary}")

    if decisions:
        lines.append("")
        lines.append(f"Decisiones activas ({len(decisions)}):")
        for d in decisions:
            lines.append(f"  • {d.title}")

    if recalls:
        lines.append("")
        lines.append(f"Recalls ({len(recalls)}):")
        for r in recalls:
            text = r.text if len(r.text) <= 120 else r.text[:117] + "..."
            lines.append(f"  • {text}")

    lines.append("")
    lines.append("Para más contexto, usa la herramienta MCP `recall(query)`.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_digest.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/digest.py tests/test_digest.py
git commit -m "feat: add digest generator for project context injection"
```

---

## Milestone 3 — Project Registry & auto-scan

**Goal:** Discover projects on disk, detect type, propose dev_command. Persisted via MemoryService.

### Task 3.1: Type detection

**Files:**
- Create: `myorch/services/project_registry.py`
- Test: `tests/test_project_registry_detect.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_project_registry_detect.py
from pathlib import Path

from myorch.services.project_registry import detect_project_type


def _make(tmp_path: Path, name: str, files: list[str]) -> Path:
    d = tmp_path / name
    d.mkdir()
    for f in files:
        (d / f).write_text("# stub\n")
    return d


def test_detect_django(tmp_path: Path):
    p = _make(tmp_path, "gate", ["manage.py"])
    info = detect_project_type(p)
    assert info["type"] == "django"
    assert "manage.py runserver" in info["dev_command"]
    assert info["dev_port"] == 8000


def test_detect_node(tmp_path: Path):
    p = _make(tmp_path, "front", ["package.json"])
    info = detect_project_type(p)
    assert info["type"] == "node"
    assert info["dev_command"] == "npm run dev"


def test_detect_python_generic(tmp_path: Path):
    p = _make(tmp_path, "lib", ["pyproject.toml"])
    info = detect_project_type(p)
    assert info["type"] == "python"


def test_detect_rust(tmp_path: Path):
    p = _make(tmp_path, "svc", ["Cargo.toml"])
    info = detect_project_type(p)
    assert info["type"] == "rust"
    assert info["dev_command"] == "cargo run"


def test_detect_unknown(tmp_path: Path):
    p = _make(tmp_path, "misc", ["README.md"])
    info = detect_project_type(p)
    assert info["type"] == "unknown"
    assert info["dev_command"] is None
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_project_registry_detect.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `myorch/services/project_registry.py`**

```python
from pathlib import Path
from typing import Any

from myorch.models import Project
from myorch.services.memory_service import MemoryService


def detect_project_type(path: Path) -> dict[str, Any]:
    """Inspect a directory and propose project type, dev_command, dev_port."""
    if (path / "manage.py").exists():
        venv_python = path / "venv" / "bin" / "python"
        runner = str(venv_python) if venv_python.exists() else "python"
        return {
            "type": "django",
            "dev_command": f"{runner} manage.py runserver [::]:8000",
            "dev_port": 8000,
        }
    if (path / "package.json").exists():
        return {"type": "node", "dev_command": "npm run dev", "dev_port": None}
    if (path / "Cargo.toml").exists():
        return {"type": "rust", "dev_command": "cargo run", "dev_port": None}
    if (path / "pyproject.toml").exists():
        return {"type": "python", "dev_command": None, "dev_port": None}
    return {"type": "unknown", "dev_command": None, "dev_port": None}


class ProjectRegistry:
    def __init__(self, memory: MemoryService, apps_root: Path):
        self.memory = memory
        self.apps_root = apps_root

    def scan(self) -> list[Project]:
        if not self.apps_root.exists():
            return []
        out: list[Project] = []
        for entry in sorted(self.apps_root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            info = detect_project_type(entry)
            project = Project(
                name=entry.name, path=str(entry),
                type=info["type"], dev_command=info["dev_command"],
                dev_port=info["dev_port"],
                metadata={"needs_review": info["type"] == "unknown"},
            )
            saved = self.memory.upsert_project(project)
            out.append(saved)
        return out
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_project_registry_detect.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/project_registry.py tests/test_project_registry_detect.py
git commit -m "feat: add project type detection for django/node/python/rust"
```

---

### Task 3.2: ProjectRegistry — full scan integration

**Files:**
- Test: `tests/test_project_registry_scan.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_project_registry_scan.py
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
```

- [ ] **Step 2: Run test (passes — already implemented)**

Run: `pytest tests/test_project_registry_scan.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_project_registry_scan.py
git commit -m "test: cover ProjectRegistry.scan persistence and idempotency"
```

---

## Milestone 4 — MCP Server (spike + impl)

**Goal:** Standalone MCP stdio server with the 6 tools, ambient project from env var.

### Task 4.0: Spike — confirm `claude_session_id` capture mechanism

**Files:** None yet — this is a research task. Document findings in `docs/superpowers/notes/2026-05-05-session-id-capture.md`.

- [ ] **Step 1: Try `claude` flags**

Run: `claude --help 2>&1 | head -100`

Expected: list of flags. Look for any flag mentioning `session-id`, `print`, `output-format`, or `json`.

- [ ] **Step 2: Try `--output-format json` headless**

Run: `cd /tmp && mkdir -p spike-claude && cd spike-claude && claude -p --output-format json "say hi"`

Expected: JSON output that should include a session_id field. Note the exact field name.

- [ ] **Step 3: Inspect `~/.claude/projects/`**

Run: `ls ~/.claude/projects/ | head -5`

Expected: directory names that look like encoded project paths. Pick one and `ls` it: should contain `.jsonl` files named with session UUIDs.

- [ ] **Step 4: Document findings**

```bash
mkdir -p docs/superpowers/notes
```

Create `docs/superpowers/notes/2026-05-05-session-id-capture.md` with:
- Which mechanism worked (flag, JSON output, or filesystem polling)
- The exact format of the session ID
- Sample command and output snippet
- The chosen capture strategy for SessionManager

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/notes/2026-05-05-session-id-capture.md
git commit -m "docs: spike findings for claude_session_id capture"
```

---

### Task 4.1: MCP server — context layer (testable in isolation)

**Files:**
- Create: `myorch/mcp_server.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_server.py
import os
from pathlib import Path

import pytest

from myorch.db import connect, init_schema
from myorch.mcp_server import McpContext, build_context
from myorch.models import Decision, Project, Recall
from myorch.services.memory_service import MemoryService


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch) -> McpContext:
    db = tmp_path / "t.db"
    conn = connect(db)
    init_schema(conn)
    m = MemoryService(conn)
    p = m.upsert_project(Project(name="alpha", path="/tmp/alpha"))
    monkeypatch.setenv("MYORCH_DB", str(db))
    monkeypatch.setenv("MYORCH_PROJECT", "alpha")
    return build_context()


def test_build_context_resolves_project_from_env(ctx: McpContext):
    assert ctx.project.name == "alpha"


def test_build_context_raises_when_env_missing(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MYORCH_PROJECT", raising=False)
    monkeypatch.setenv("MYORCH_DB", str(tmp_path / "t.db"))
    with pytest.raises(RuntimeError, match="MYORCH_PROJECT"):
        build_context()


def test_recall_tool_returns_hits(ctx: McpContext):
    ctx.memory.save_decision(
        ctx.project.id,
        Decision(project_id=ctx.project.id, title="JWT", body="use simplejwt"),
    )
    hits = ctx.recall("JWT", limit=5)
    assert len(hits) == 1


def test_save_decision_tool_persists(ctx: McpContext):
    new_id = ctx.save_decision(title="Postgres", body="not sqlite", tags=["db"])
    assert new_id > 0
    decisions = ctx.memory.list_decisions(ctx.project.id)
    assert any(d.title == "Postgres" for d in decisions)


def test_save_recall_tool_persists(ctx: McpContext):
    new_id = ctx.save_recall(text="port 8000", tags=["dev"])
    assert new_id > 0
    recalls = ctx.memory.list_recalls(ctx.project.id)
    assert any(r.text == "port 8000" for r in recalls)


def test_save_summary_writes_to_active_session(ctx: McpContext):
    s = ctx.memory.start_session(ctx.project.id)
    ctx.active_session_id = s.id
    ctx.save_summary(summary="did stuff", files_touched=["a.py"])
    s2 = ctx.memory.get_session(s.id)
    assert s2.summary == "did stuff"
    assert s2.files_touched == ["a.py"]


def test_list_recent_sessions_tool(ctx: McpContext):
    ctx.memory.start_session(ctx.project.id)
    out = ctx.list_recent_sessions(limit=5)
    assert len(out) == 1


def test_list_decisions_tool_filters_by_tag(ctx: McpContext):
    ctx.save_decision(title="A", body="x", tags=["auth"])
    ctx.save_decision(title="B", body="y", tags=["db"])
    only_auth = ctx.list_decisions(tag="auth")
    assert len(only_auth) == 1
    assert only_auth[0].title == "A"
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `myorch/mcp_server.py`**

```python
"""MCP server (stdio mode) spawned by `claude` per session.

Reads MYORCH_DB and MYORCH_PROJECT from env. Exposes 6 tools:
  recall, list_recent_sessions, list_decisions, save_decision, save_recall, save_summary

The active session id is written by Session Manager to a sidecar file
(~/.myorch/run/<project>.session). save_summary reads that file at call time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from myorch.db import connect, init_schema
from myorch.models import Decision, Project, Recall, RecallHit, SessionBrief
from myorch.services.memory_service import MemoryService


@dataclass
class McpContext:
    memory: MemoryService
    project: Project
    active_session_id: int | None = None

    def _resolve_session_id(self) -> int | None:
        if self.active_session_id is not None:
            return self.active_session_id
        sidecar = Path(os.environ.get(
            "MYORCH_SESSION_FILE",
            str(Path.home() / ".myorch" / "run" / f"{self.project.name}.session"),
        ))
        if sidecar.exists():
            try:
                return int(sidecar.read_text().strip())
            except ValueError:
                return None
        return None

    def recall(self, query: str, limit: int = 10) -> list[RecallHit]:
        return self.memory.recall(self.project.id, query, limit=limit)  # type: ignore[arg-type]

    def list_recent_sessions(self, limit: int = 5) -> list[SessionBrief]:
        return self.memory.list_recent_sessions(self.project.id, limit=limit)  # type: ignore[arg-type]

    def list_decisions(self, tag: str | None = None) -> list[Decision]:
        return self.memory.list_decisions(self.project.id, tag=tag)  # type: ignore[arg-type]

    def save_decision(self, title: str, body: str, tags: list[str] | None = None) -> int:
        d = self.memory.save_decision(
            self.project.id,  # type: ignore[arg-type]
            Decision(project_id=self.project.id, title=title, body=body, tags=tags or []),  # type: ignore[arg-type]
        )
        return d.id  # type: ignore[return-value]

    def save_recall(self, text: str, tags: list[str] | None = None) -> int:
        r = self.memory.save_recall(
            self.project.id,  # type: ignore[arg-type]
            Recall(project_id=self.project.id, text=text, tags=tags or []),  # type: ignore[arg-type]
        )
        return r.id  # type: ignore[return-value]

    def save_summary(self, summary: str, files_touched: list[str] | None = None) -> None:
        sid = self._resolve_session_id()
        if sid is None:
            raise RuntimeError("No active session — cannot save summary")
        self.memory.save_summary(sid, summary, files_touched or [])


def build_context() -> McpContext:
    db_path = os.environ.get("MYORCH_DB")
    project_name = os.environ.get("MYORCH_PROJECT")
    if not db_path:
        raise RuntimeError("MYORCH_DB env var not set")
    if not project_name:
        raise RuntimeError("MYORCH_PROJECT env var not set")
    conn = connect(Path(db_path))
    init_schema(conn)
    memory = MemoryService(conn)
    project = memory.get_project_by_name(project_name)
    if project is None:
        raise RuntimeError(f"Project {project_name!r} not found in DB")
    return McpContext(memory=memory, project=project)
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_mcp_server.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add MCP context with 6 tool implementations + sidecar session resolution"
```

---

### Task 4.2: MCP server — wire to FastMCP stdio

**Files:**
- Modify: `myorch/mcp_server.py` (add `__main__` and FastMCP wiring)
- Test: `tests/test_mcp_server_stdio.py`

- [ ] **Step 1: Write the failing test (smoke)**

```python
# tests/test_mcp_server_stdio.py
import json
import subprocess
import sys
from pathlib import Path


def test_mcp_server_responds_to_initialize(tmp_path: Path):
    """End-to-end: spawn the MCP server as subprocess, send initialize, expect response."""
    db = tmp_path / "t.db"
    from myorch.db import connect, init_schema
    from myorch.models import Project
    from myorch.services.memory_service import MemoryService
    conn = connect(db)
    init_schema(conn)
    MemoryService(conn).upsert_project(Project(name="alpha", path="/tmp/alpha"))
    conn.close()

    env = {
        "MYORCH_DB": str(db),
        "MYORCH_PROJECT": "alpha",
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path.cwd()),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "myorch.mcp_server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True,
    )
    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {}, "clientInfo": {"name": "test", "version": "0.1"},
        },
    }) + "\n"
    proc.stdin.write(request)
    proc.stdin.flush()
    line = proc.stdout.readline()
    proc.terminate()
    proc.wait(timeout=5)
    assert line, f"no response. stderr: {proc.stderr.read()}"
    resp = json.loads(line)
    assert resp.get("id") == 1
    assert "result" in resp
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_mcp_server_stdio.py -v`
Expected: FAIL — no `__main__`.

- [ ] **Step 3: Add FastMCP wiring at the bottom of `myorch/mcp_server.py`**

```python
def main() -> None:
    from mcp.server.fastmcp import FastMCP

    ctx = build_context()
    mcp = FastMCP("myorch-memory")

    @mcp.tool()
    def recall(query: str, limit: int = 10) -> list[dict]:
        """Búsqueda full-text sobre memoria del proyecto activo."""
        return [h.model_dump() for h in ctx.recall(query, limit=limit)]

    @mcp.tool()
    def list_recent_sessions(limit: int = 5) -> list[dict]:
        """Las últimas N sesiones del proyecto activo con su resumen."""
        return [s.model_dump() for s in ctx.list_recent_sessions(limit=limit)]

    @mcp.tool()
    def list_decisions(tag: str | None = None) -> list[dict]:
        """Decisiones del proyecto activo, opcionalmente filtradas por tag."""
        return [d.model_dump() for d in ctx.list_decisions(tag=tag)]

    @mcp.tool()
    def save_decision(title: str, body: str, tags: list[str] | None = None) -> int:
        """Registra una decisión razonada. Devuelve el ID de la decisión."""
        return ctx.save_decision(title=title, body=body, tags=tags)

    @mcp.tool()
    def save_recall(text: str, tags: list[str] | None = None) -> int:
        """Nota rápida ('no olvides X'). Devuelve el ID."""
        return ctx.save_recall(text=text, tags=tags)

    @mcp.tool()
    def save_summary(summary: str, files_touched: list[str] | None = None) -> str:
        """Guarda el resumen de la sesión activa. Llamado por el hook Stop."""
        ctx.save_summary(summary=summary, files_touched=files_touched)
        return "ok"

    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_mcp_server_stdio.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/mcp_server.py tests/test_mcp_server_stdio.py
git commit -m "feat: wire MCP tools via FastMCP stdio transport"
```

---

## Milestone 5 — Session Manager (PTY)

**Goal:** Spawn `claude` in a PTY, bridge stdin/stdout to memory and to a queue consumable by WebSockets.

### Task 5.1: PTY wrapper

**Files:**
- Create: `myorch/services/session_manager.py`
- Test: `tests/test_session_manager_pty.py`

- [ ] **Step 1: Write the failing test (uses `cat` as a stand-in for `claude`)**

```python
# tests/test_session_manager_pty.py
import time
from pathlib import Path

import pytest

from myorch.services.session_manager import PtySession


def test_pty_writes_and_reads_with_cat():
    session = PtySession(["cat"], cwd=str(Path.home()))
    session.spawn()
    try:
        session.write("hello\n")
        deadline = time.time() + 2.0
        out = ""
        while time.time() < deadline and "hello" not in out:
            chunk = session.read_nonblocking(timeout=0.2)
            if chunk:
                out += chunk
        assert "hello" in out
    finally:
        session.terminate()


def test_pty_terminate_kills_process():
    session = PtySession(["sleep", "30"], cwd="/tmp")
    session.spawn()
    assert session.is_alive()
    session.terminate()
    deadline = time.time() + 3.0
    while session.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    assert not session.is_alive()
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_session_manager_pty.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `myorch/services/session_manager.py` (PTY layer)**

```python
from __future__ import annotations

import signal
from typing import Sequence

import pexpect


class PtySession:
    """Thin wrapper around pexpect.spawn for one PTY-managed subprocess."""

    def __init__(self, argv: Sequence[str], cwd: str, env: dict[str, str] | None = None):
        self.argv = list(argv)
        self.cwd = cwd
        self.env = env
        self._proc: pexpect.spawn | None = None

    def spawn(self) -> None:
        self._proc = pexpect.spawn(
            self.argv[0], args=self.argv[1:], cwd=self.cwd, env=self.env,
            encoding="utf-8", timeout=None, dimensions=(40, 120),
        )

    def write(self, data: str) -> None:
        if self._proc is None:
            raise RuntimeError("not spawned")
        self._proc.send(data)

    def read_nonblocking(self, timeout: float = 0.1) -> str:
        if self._proc is None:
            return ""
        try:
            return self._proc.read_nonblocking(size=4096, timeout=timeout)
        except pexpect.TIMEOUT:
            return ""
        except pexpect.EOF:
            return ""

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.isalive()

    def terminate(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.kill(signal.SIGTERM)
            self._proc.wait()
        except Exception:
            try:
                self._proc.kill(signal.SIGKILL)
            except Exception:
                pass
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_session_manager_pty.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/session_manager.py tests/test_session_manager_pty.py
git commit -m "feat: PtySession wrapper around pexpect with read/write/terminate"
```

---

### Task 5.2: SessionManager — open/close session lifecycle

**Files:**
- Modify: `myorch/services/session_manager.py`
- Test: `tests/test_session_manager_lifecycle.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_manager_lifecycle.py
import time
from pathlib import Path

import pytest

from myorch.config import Settings
from myorch.db import connect, init_schema
from myorch.models import Project, SessionStatus
from myorch.services.memory_service import MemoryService
from myorch.services.session_manager import SessionManager


@pytest.fixture
def manager(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    monkeypatch.setenv("MYORCH_TMP_DIR", str(tmp_path / "tmp"))
    settings = Settings()
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    proj_dir = tmp_path / "alpha"
    proj_dir.mkdir()
    p = memory.upsert_project(Project(name="alpha", path=str(proj_dir)))
    mgr = SessionManager(memory=memory, settings=settings,
                         claude_argv_factory=lambda **kw: ["cat"])
    return mgr, memory, p.id  # type: ignore[return-value]


def test_open_session_creates_active_db_row_and_sidecar(manager):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    try:
        s = memory.get_session(handle.session_id)
        assert s.status == SessionStatus.active
        sidecar = mgr.settings.data_dir / "run" / "alpha.session"
        assert sidecar.exists()
        assert sidecar.read_text().strip() == str(handle.session_id)
    finally:
        mgr.close(handle.session_id)


def test_close_session_terminates_and_marks_closed(manager):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    mgr.close(handle.session_id)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        s = memory.get_session(handle.session_id)
        if s.status == SessionStatus.closed:
            return
        time.sleep(0.05)
    pytest.fail("session not marked closed in time")


def test_open_writes_digest_file(manager):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    try:
        digest_path = Path(memory.get_project_by_id(pid).path) / ".myorch" / "CLAUDE.context.md"
        assert digest_path.exists()
        assert "alpha" in digest_path.read_text()
    finally:
        mgr.close(handle.session_id)
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_session_manager_lifecycle.py -v`
Expected: FAIL — `SessionManager` not yet defined.

- [ ] **Step 3: Add `SessionManager` class to `myorch/services/session_manager.py`**

Add imports at top:

```python
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from myorch.config import Settings
from myorch.digest import generate_digest
from myorch.models import SessionStatus
from myorch.services.memory_service import MemoryService
```

Add at bottom:

```python
@dataclass
class SessionHandle:
    session_id: int
    project_id: int
    pty: PtySession


class SessionManager:
    """Owns the lifecycle of one PTY-backed `claude` process per project."""

    def __init__(
        self,
        memory: MemoryService,
        settings: Settings,
        claude_argv_factory=None,
    ):
        self.memory = memory
        self.settings = settings
        self._claude_argv_factory = claude_argv_factory or _default_claude_argv
        self._handles: dict[int, SessionHandle] = {}
        self._lock = Lock()

    def open(self, project_id: int) -> SessionHandle:
        with self._lock:
            project = self.memory.get_project_by_id(project_id)
            if project is None:
                raise ValueError(f"project {project_id} not found")
            myorch_dir = Path(project.path) / ".myorch"
            myorch_dir.mkdir(exist_ok=True)
            digest_path = myorch_dir / "CLAUDE.context.md"
            digest_path.write_text(generate_digest(self.memory, project_id))
            session = self.memory.start_session(project_id)
            run_dir = self.settings.data_dir / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / f"{project.name}.session").write_text(str(session.id))
            argv = self._claude_argv_factory(
                project=project, digest_path=digest_path,
                resume_id=project.last_session_id,
            )
            env = {**os.environ,
                   "MYORCH_DB": str(self.settings.db_path),
                   "MYORCH_PROJECT": project.name}
            pty = PtySession(argv=argv, cwd=project.path, env=env)
            pty.spawn()
            handle = SessionHandle(session_id=session.id, project_id=project_id, pty=pty)  # type: ignore[arg-type]
            self._handles[session.id] = handle  # type: ignore[index]
            return handle

    def close(self, session_id: int, status: SessionStatus = SessionStatus.closed) -> None:
        with self._lock:
            handle = self._handles.pop(session_id, None)
        if handle:
            handle.pty.terminate()
        self.memory.close_session(session_id, status=status)

    def get(self, session_id: int) -> SessionHandle | None:
        return self._handles.get(session_id)


def _default_claude_argv(project, digest_path: Path, resume_id: str | None) -> list[str]:
    argv = ["claude"]
    if resume_id:
        argv.extend(["--resume", resume_id])
    argv.extend(["--mcp-config", str(Path.home() / ".myorch" / "mcp.json")])
    argv.extend(["--append-system-prompt", f"@{digest_path}"])
    return argv
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_session_manager_lifecycle.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/session_manager.py tests/test_session_manager_lifecycle.py
git commit -m "feat: SessionManager opens/closes claude PTYs with sidecar + digest injection"
```

---

### Task 5.3: SessionManager — Stop hook for auto-summary

**Files:**
- Modify: `myorch/services/session_manager.py` (add `request_summary_and_close`)
- Test: `tests/test_session_manager_summary.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_manager_summary.py
import threading
import time
from pathlib import Path

import pytest

from myorch.config import Settings
from myorch.db import connect, init_schema
from myorch.models import Project, SessionStatus
from myorch.services.memory_service import MemoryService
from myorch.services.session_manager import SessionManager


@pytest.fixture
def manager(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    settings = Settings()
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    proj_dir = tmp_path / "alpha"
    proj_dir.mkdir()
    p = memory.upsert_project(Project(name="alpha", path=str(proj_dir)))
    mgr = SessionManager(memory=memory, settings=settings,
                         claude_argv_factory=lambda **kw: ["cat"])
    return mgr, memory, p.id


def test_request_summary_writes_prompt_to_pty_and_waits(manager, monkeypatch):
    mgr, memory, pid = manager
    handle = mgr.open(project_id=pid)
    written: list[str] = []
    monkeypatch.setattr(handle.pty, "write", lambda s: written.append(s))

    def fake_save():
        time.sleep(0.05)
        memory.save_summary(handle.session_id, "did things", ["file.py"])

    threading.Thread(target=fake_save).start()
    mgr.request_summary_and_close(handle.session_id, timeout=2.0)
    assert any("save_summary" in w for w in written)
    s = memory.get_session(handle.session_id)
    assert s.summary == "did things"
    assert s.status == SessionStatus.closed
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_session_manager_summary.py -v`
Expected: FAIL — `request_summary_and_close` does not exist.

- [ ] **Step 3: Add method to `SessionManager`**

```python
    def request_summary_and_close(self, session_id: int, timeout: float = 30.0) -> None:
        """Send the Stop hook prompt and wait up to `timeout` for save_summary to land."""
        import time
        handle = self._handles.get(session_id)
        if handle is None:
            self.memory.close_session(session_id)
            return
        prompt = (
            "\n[SISTEMA: la sesión está por cerrar. Llama AHORA a la tool MCP "
            "`save_summary(summary=..., files_touched=[...])` con un resumen de máximo "
            "5 líneas de lo trabajado, archivos tocados y decisiones nuevas. "
            "Después de hacerlo, no escribas nada más.]\n"
        )
        try:
            handle.pty.write(prompt)
        except Exception:
            pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            s = self.memory.get_session(session_id)
            if s and s.summary:
                break
            time.sleep(0.1)
        self.close(session_id)
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_session_manager_summary.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/session_manager.py tests/test_session_manager_summary.py
git commit -m "feat: SessionManager.request_summary_and_close triggers Stop-hook flow"
```

---

## Milestone 6 — Dev Server Manager

**Goal:** start/stop subprocesses, ring buffer of logs, queryable per-project state.

### Task 6.1: Ring buffer

**Files:**
- Create: `myorch/services/dev_server_manager.py`
- Test: `tests/test_ring_buffer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ring_buffer.py
from myorch.services.dev_server_manager import RingBuffer


def test_ring_buffer_appends_lines():
    rb = RingBuffer(capacity=3)
    rb.append("a")
    rb.append("b")
    assert rb.tail() == ["a", "b"]


def test_ring_buffer_drops_oldest():
    rb = RingBuffer(capacity=3)
    for ch in "abcde":
        rb.append(ch)
    assert rb.tail() == ["c", "d", "e"]


def test_ring_buffer_clear():
    rb = RingBuffer(capacity=3)
    rb.append("x")
    rb.clear()
    assert rb.tail() == []
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_ring_buffer.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `RingBuffer` in `myorch/services/dev_server_manager.py`**

```python
from collections import deque
from threading import Lock


class RingBuffer:
    def __init__(self, capacity: int):
        self._dq: deque[str] = deque(maxlen=capacity)
        self._lock = Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self._dq.append(line)

    def tail(self) -> list[str]:
        with self._lock:
            return list(self._dq)

    def clear(self) -> None:
        with self._lock:
            self._dq.clear()
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_ring_buffer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/dev_server_manager.py tests/test_ring_buffer.py
git commit -m "feat: add RingBuffer for dev server log tailing"
```

---

### Task 6.2: DevServerManager start/stop

**Files:**
- Modify: `myorch/services/dev_server_manager.py`
- Test: `tests/test_dev_server_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dev_server_manager.py
import time
from pathlib import Path

from myorch.services.dev_server_manager import DevServerManager


def test_start_runs_command_and_captures_output(tmp_path: Path):
    mgr = DevServerManager()
    mgr.start(project_id=1, command="echo hello && sleep 1", cwd=str(tmp_path))
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if any("hello" in line for line in mgr.tail(1)):
            break
        time.sleep(0.05)
    assert any("hello" in line for line in mgr.tail(1))
    mgr.stop(1)


def test_stop_kills_running_process(tmp_path: Path):
    mgr = DevServerManager()
    mgr.start(project_id=2, command="sleep 30", cwd=str(tmp_path))
    assert mgr.is_running(2)
    mgr.stop(2)
    deadline = time.time() + 5.0
    while mgr.is_running(2) and time.time() < deadline:
        time.sleep(0.05)
    assert not mgr.is_running(2)


def test_double_start_replaces_previous(tmp_path: Path):
    mgr = DevServerManager()
    mgr.start(project_id=3, command="sleep 30", cwd=str(tmp_path))
    pid_a = mgr._procs[3].popen.pid
    mgr.start(project_id=3, command="sleep 30", cwd=str(tmp_path))
    pid_b = mgr._procs[3].popen.pid
    assert pid_a != pid_b
    mgr.stop(3)
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_dev_server_manager.py -v`
Expected: FAIL — `DevServerManager` missing.

- [ ] **Step 3: Implement `DevServerManager`**

Add to `myorch/services/dev_server_manager.py`:

```python
import os
import signal
import subprocess
import threading
from dataclasses import dataclass


@dataclass
class _DevProc:
    popen: subprocess.Popen
    buffer: RingBuffer
    reader: threading.Thread


class DevServerManager:
    def __init__(self, buffer_capacity: int = 500):
        self._procs: dict[int, _DevProc] = {}
        self._buffer_capacity = buffer_capacity
        self._lock = threading.Lock()

    def start(self, project_id: int, command: str, cwd: str) -> None:
        with self._lock:
            self._stop_unlocked(project_id)
            buf = RingBuffer(capacity=self._buffer_capacity)
            popen = subprocess.Popen(
                command, cwd=cwd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                preexec_fn=os.setsid,
            )

            def reader():
                try:
                    assert popen.stdout is not None
                    for line in iter(popen.stdout.readline, ""):
                        if not line:
                            break
                        buf.append(line.rstrip("\n"))
                finally:
                    if popen.stdout:
                        popen.stdout.close()

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            self._procs[project_id] = _DevProc(popen=popen, buffer=buf, reader=t)

    def stop(self, project_id: int) -> None:
        with self._lock:
            self._stop_unlocked(project_id)

    def _stop_unlocked(self, project_id: int) -> None:
        proc = self._procs.pop(project_id, None)
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.popen.pid), signal.SIGTERM)
            proc.popen.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.popen.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass

    def is_running(self, project_id: int) -> bool:
        proc = self._procs.get(project_id)
        return proc is not None and proc.popen.poll() is None

    def tail(self, project_id: int) -> list[str]:
        proc = self._procs.get(project_id)
        return proc.buffer.tail() if proc else []

    def shutdown_all(self) -> None:
        with self._lock:
            for pid in list(self._procs.keys()):
                self._stop_unlocked(pid)
```

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_dev_server_manager.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/dev_server_manager.py tests/test_dev_server_manager.py
git commit -m "feat: DevServerManager with subprocess group lifecycle and tail buffer"
```

---

## Milestone 7 — FastAPI app + routers (REST + WS)

**Goal:** HTTP endpoints + WebSocket streaming. Templates render HTML fragments for HTMX. All HTML rendering through Jinja2 (auto-escaping).

### Task 7.1: FastAPI app skeleton

**Files:**
- Create: `myorch/app.py`
- Create: `myorch/templates/base.html`
- Create: `myorch/templates/workspace.html`
- Test: `tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app_smoke.py
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
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_app_smoke.py -v`
Expected: FAIL.

- [ ] **Step 3: Create templates**

`myorch/templates/base.html`:
```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>{% block title %}MyOrchestrator{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css" />
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
  <script src="/static/app.js" defer></script>
</head>
<body class="bg-zinc-900 text-zinc-100 min-h-screen">
{% block body %}{% endblock %}
</body>
</html>
```

`myorch/templates/workspace.html`:
```html
{% extends "base.html" %}
{% block body %}
<div class="flex h-screen">
  <aside class="w-60 bg-zinc-800 border-r border-zinc-700 p-2">
    <h1 class="text-lg font-bold">MyOrchestrator</h1>
    <div id="project-list" hx-get="/projects" hx-trigger="load" hx-swap="innerHTML"></div>
    <button class="mt-2 text-xs px-2 py-1 bg-zinc-700 rounded"
            hx-post="/projects/scan" hx-target="#project-list">+ Scan</button>
  </aside>
  <main class="flex-1 p-4" id="workspace">
    <p class="text-zinc-400">Selecciona un proyecto del sidebar.</p>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 4: Implement `myorch/app.py`**

```python
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from myorch.config import get_settings
from myorch.db import connect, init_schema
from myorch.services.dev_server_manager import DevServerManager
from myorch.services.memory_service import MemoryService
from myorch.services.project_registry import ProjectRegistry
from myorch.services.session_manager import SessionManager


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    registry = ProjectRegistry(memory, settings.apps_root)
    session_mgr = SessionManager(memory=memory, settings=settings)
    dev_mgr = DevServerManager()

    base = Path(__file__).parent
    templates = Jinja2Templates(directory=str(base / "templates"))
    app = FastAPI(title="MyOrchestrator")
    app.mount("/static", StaticFiles(directory=str(base / "static")), name="static")

    app.state.settings = settings
    app.state.memory = memory
    app.state.registry = registry
    app.state.session_mgr = session_mgr
    app.state.dev_mgr = dev_mgr
    app.state.templates = templates

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse("workspace.html", {"request": request})

    @app.get("/health")
    async def health():
        return {
            "ok": True,
            "claude_cli": shutil.which("claude") is not None,
            "apps_root_exists": settings.apps_root.exists(),
            "db_path": str(settings.db_path),
        }

    from myorch.routers import devservers, memory as mem_router, projects, sessions
    app.include_router(projects.router)
    app.include_router(sessions.router)
    app.include_router(devservers.router)
    app.include_router(mem_router.router)

    @app.on_event("shutdown")
    async def _shutdown():
        dev_mgr.shutdown_all()

    return app
```

- [ ] **Step 5: Stub the routers and create static dir**

```bash
mkdir -p myorch/routers myorch/static
touch myorch/routers/__init__.py
echo "// placeholder" > myorch/static/app.js
```

For each of `projects.py`, `sessions.py`, `devservers.py`, `memory.py` — create a stub with just an `APIRouter()`:

`myorch/routers/projects.py`:
```python
from fastapi import APIRouter
router = APIRouter(prefix="/projects", tags=["projects"])
```

Repeat for the other three (`sessions.py` prefix `/sessions`, `devservers.py` prefix `/devservers`, `memory.py` prefix `/memory`).

- [ ] **Step 6: Run test (passes)**

Run: `pytest tests/test_app_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add myorch/app.py myorch/templates/ myorch/routers/ myorch/static/
git add tests/test_app_smoke.py
git commit -m "feat: FastAPI app skeleton with templates and router stubs"
```

---

### Task 7.2: Projects router

**Files:**
- Modify: `myorch/routers/projects.py`
- Create: `myorch/templates/partials/project_list.html`
- Test: `tests/test_router_projects.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router_projects.py
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
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_router_projects.py -v`
Expected: FAIL — endpoints not defined.

- [ ] **Step 3: Implement `myorch/routers/projects.py`**

```python
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_class=HTMLResponse)
async def list_projects(request: Request):
    memory = request.app.state.memory
    templates = request.app.state.templates
    projects = memory.list_projects()
    return templates.TemplateResponse(
        "partials/project_list.html",
        {"request": request, "projects": projects},
    )


@router.post("/scan", response_class=HTMLResponse)
async def scan(request: Request):
    request.app.state.registry.scan()
    return await list_projects(request)


@router.get("/{name}")
async def get_project(name: str, request: Request):
    p = request.app.state.memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(p.model_dump(mode="json"))


@router.patch("/{name}")
async def update_project(
    name: str, request: Request,
    dev_command: str | None = Form(None),
    dev_port: int | None = Form(None),
    description: str | None = Form(None),
):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    fields = {k: v for k, v in {"dev_command": dev_command,
                                "dev_port": dev_port,
                                "description": description}.items() if v is not None}
    if fields:
        memory.update_project(p.id, **fields)
    return JSONResponse(memory.get_project_by_name(name).model_dump(mode="json"))
```

- [ ] **Step 4: Create partial template**

```bash
mkdir -p myorch/templates/partials
```

`myorch/templates/partials/project_list.html`:
```html
<ul class="space-y-1 text-sm">
  {% for p in projects %}
  <li class="flex items-center gap-2 px-2 py-1 hover:bg-zinc-700 rounded cursor-pointer"
      hx-get="/sessions/workspace/{{ p.name }}" hx-target="#workspace">
    <span class="w-2 h-2 rounded-full bg-zinc-500"></span>
    <span>{{ p.name }}</span>
    {% if p.metadata.get("needs_review") %}
    <span class="ml-auto text-xs text-amber-400">review</span>
    {% endif %}
  </li>
  {% endfor %}
</ul>
```

- [ ] **Step 5: Run test (passes)**

Run: `pytest tests/test_router_projects.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add myorch/routers/projects.py myorch/templates/partials/ tests/test_router_projects.py
git commit -m "feat: projects router with scan, list, get, patch + HTMX partial"
```

---

### Task 7.3: Sessions router + WebSocket bridge

**Files:**
- Modify: `myorch/routers/sessions.py`
- Create: `myorch/templates/partials/workspace_panel.html`
- Test: `tests/test_router_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router_sessions.py
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
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_router_sessions.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `myorch/routers/sessions.py`**

```python
import asyncio
import json
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024


class OpenSessionRequest(BaseModel):
    project: str


@router.get("/workspace/{name}", response_class=HTMLResponse)
async def workspace(name: str, request: Request):
    memory = request.app.state.memory
    templates = request.app.state.templates
    project = memory.get_project_by_name(name)
    if project is None:
        return HTMLResponse("not found", status_code=404)
    return templates.TemplateResponse(
        "partials/workspace_panel.html",
        {"request": request, "project": project},
    )


@router.post("/open")
async def open_session(req: OpenSessionRequest, request: Request):
    memory = request.app.state.memory
    project = memory.get_project_by_name(req.project)
    if project is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    handle = request.app.state.session_mgr.open(project_id=project.id)
    return JSONResponse({"session_id": handle.session_id, "project": project.name})


@router.post("/{session_id}/close")
async def close_session(session_id: int, request: Request):
    request.app.state.session_mgr.request_summary_and_close(session_id)
    return {"ok": True}


@router.post("/{session_id}/upload-image")
async def upload_image(session_id: int, request: Request, file: UploadFile = File(...)):
    settings = request.app.state.settings
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image > 5MB")
    sess_dir = settings.tmp_dir / str(session_id)
    sess_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if (file.content_type or "").endswith("png") else ".bin"
    fname = f"{uuid.uuid4().hex}{suffix}"
    path = sess_dir / fname
    path.write_bytes(data)
    return {"path": str(path)}


@router.websocket("/ws/{session_id}")
async def ws_session(ws: WebSocket, session_id: int):
    await ws.accept()
    mgr = ws.app.state.session_mgr
    handle = mgr.get(session_id)
    if handle is None:
        await ws.send_text(json.dumps({"error": "session not found"}))
        await ws.close()
        return

    async def pump_pty_to_ws():
        while True:
            chunk = await asyncio.to_thread(handle.pty.read_nonblocking, 0.1)
            if chunk:
                await ws.send_text(chunk)
            else:
                await asyncio.sleep(0.05)
            if not handle.pty.is_alive():
                await ws.send_text("\n[session ended]\n")
                break

    pump_task = asyncio.create_task(pump_pty_to_ws())
    try:
        while True:
            data = await ws.receive_text()
            handle.pty.write(data)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
```

- [ ] **Step 4: Add `partials/workspace_panel.html`**

```html
<div class="flex gap-3 h-full">
  <div class="flex-1 flex flex-col">
    <div class="text-sm border-b border-zinc-700 pb-2 mb-2">
      <span class="font-bold">▶ {{ project.name }}</span>
      <span class="text-zinc-400 ml-2">{{ project.path }}</span>
      <span class="text-zinc-500 ml-2">{{ project.type }}</span>
    </div>
    <div id="terminal" class="flex-1 bg-black"
         data-project="{{ project.name }}"
         hx-post="/sessions/open"
         hx-trigger="load"
         hx-vals='{"project": "{{ project.name }}"}'
         hx-swap="none"
         hx-on::after-request="window.attachTerminal(event.detail.xhr.response)"></div>
    <div class="mt-2 flex gap-2">
      <textarea id="msg-input" class="flex-1 bg-zinc-800 px-2 py-1 rounded"
                rows="2" placeholder="Mensaje (Enter envía, Shift+Enter nueva línea)"></textarea>
      <button class="px-3 py-1 bg-blue-600 rounded" onclick="window.sendMsg()">Send</button>
    </div>
    <div class="mt-3 border-t border-zinc-700 pt-2">
      <div class="flex items-center gap-2 text-sm">
        <span class="font-bold">DEV SERVER</span>
        <button class="px-2 py-0.5 bg-green-700 rounded text-xs"
                hx-post="/devservers/{{ project.name }}/start" hx-swap="none">▶ Start</button>
        <button class="px-2 py-0.5 bg-red-700 rounded text-xs"
                hx-post="/devservers/{{ project.name }}/stop" hx-swap="none">⏹ Stop</button>
        <span class="text-zinc-500 text-xs">{{ project.dev_command or "(sin comando)" }}</span>
      </div>
      <pre id="devserver-tail" class="bg-black h-32 overflow-auto text-xs p-2 mt-1"
           hx-get="/devservers/{{ project.name }}/tail"
           hx-trigger="every 2s"
           hx-swap="innerHTML"></pre>
    </div>
  </div>
  <aside class="w-72 border-l border-zinc-700 pl-3 text-sm overflow-auto">
    <h3 class="font-bold mb-2">Memoria</h3>
    <div class="text-xs text-zinc-400 mb-1">Decisiones</div>
    <div hx-get="/memory/{{ project.name }}/decisions" hx-trigger="load" hx-swap="innerHTML"></div>
    <div class="text-xs text-zinc-400 mt-3 mb-1">Recalls</div>
    <div hx-get="/memory/{{ project.name }}/recalls" hx-trigger="load" hx-swap="innerHTML"></div>
    <div class="mt-4">
      <input id="mem-search" placeholder="Buscar en memoria..."
             class="w-full bg-zinc-800 px-2 py-1 rounded text-sm"
             hx-get="/memory/{{ project.name }}/search"
             hx-trigger="keyup changed delay:300ms"
             hx-target="#mem-search-results"
             name="q">
      <div id="mem-search-results" class="text-xs mt-1"></div>
    </div>
  </aside>
</div>
```

- [ ] **Step 5: Run test (passes)**

Run: `pytest tests/test_router_sessions.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add myorch/routers/sessions.py myorch/templates/partials/workspace_panel.html
git add tests/test_router_sessions.py
git commit -m "feat: sessions router with PTY-bridged WebSocket, image upload, workspace partial"
```

---

### Task 7.4: Memory router (Jinja-rendered, no f-string HTML)

**Files:**
- Modify: `myorch/routers/memory.py`
- Create: `myorch/templates/partials/decisions_list.html`
- Create: `myorch/templates/partials/recalls_list.html`
- Create: `myorch/templates/partials/search_results.html`
- Test: `tests/test_router_memory.py`

**Note:** Decision/recall content is user/agent-supplied. Render through Jinja2 templates so values are auto-escaped — never via Python f-string concatenation.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router_memory.py
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
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_router_memory.py -v`
Expected: FAIL.

- [ ] **Step 3: Create partial templates (Jinja auto-escapes by default)**

`myorch/templates/partials/decisions_list.html`:
```html
<ul class="space-y-1">
  {% for d in decisions %}
  <li class="py-1">
    <div class="font-semibold">{{ d.title }}</div>
    <div class="text-xs text-zinc-400">{{ d.body }}</div>
  </li>
  {% endfor %}
</ul>
```

`myorch/templates/partials/recalls_list.html`:
```html
<ul class="space-y-1">
  {% for r in recalls %}
  <li class="py-1 text-sm">{{ r.text }}</li>
  {% endfor %}
</ul>
```

`myorch/templates/partials/search_results.html`:
```html
<ul class="space-y-1">
  {% for h in hits %}
  <li class="py-1 text-xs">
    <span class="text-zinc-500">{{ h.origin }}</span>
    {{ h.snippet }}
  </li>
  {% endfor %}
</ul>
```

- [ ] **Step 4: Implement `myorch/routers/memory.py`**

```python
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from myorch.models import Decision, Recall

router = APIRouter(prefix="/memory", tags=["memory"])


def _project_or_404(request: Request, name: str):
    return request.app.state.memory.get_project_by_name(name)


@router.get("/{name}/decisions", response_class=HTMLResponse)
async def list_decisions(name: str, request: Request):
    p = _project_or_404(request, name)
    if p is None:
        return HTMLResponse("not found", status_code=404)
    decisions = request.app.state.memory.list_decisions(p.id)
    return request.app.state.templates.TemplateResponse(
        "partials/decisions_list.html",
        {"request": request, "decisions": decisions},
    )


@router.get("/{name}/recalls", response_class=HTMLResponse)
async def list_recalls(name: str, request: Request):
    p = _project_or_404(request, name)
    if p is None:
        return HTMLResponse("not found", status_code=404)
    recalls = request.app.state.memory.list_recalls(p.id)
    return request.app.state.templates.TemplateResponse(
        "partials/recalls_list.html",
        {"request": request, "recalls": recalls},
    )


@router.get("/{name}/search")
async def search(name: str, q: str, request: Request, limit: int = 10):
    p = _project_or_404(request, name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    hits = request.app.state.memory.recall(p.id, q, limit=limit)
    accept = request.headers.get("accept", "")
    if "text/html" in accept or request.headers.get("hx-request") == "true":
        return request.app.state.templates.TemplateResponse(
            "partials/search_results.html",
            {"request": request, "hits": hits},
        )
    return JSONResponse({"hits": [h.model_dump() for h in hits]})


@router.post("/{name}/decisions")
async def create_decision(
    name: str, request: Request,
    title: str = Form(...), body: str = Form(...), tags: str = Form(""),
):
    p = _project_or_404(request, name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    d = request.app.state.memory.save_decision(
        p.id,
        Decision(project_id=p.id, title=title, body=body,
                 tags=[t.strip() for t in tags.split(",") if t.strip()]),
    )
    return JSONResponse(d.model_dump(mode="json"))


@router.post("/{name}/recalls")
async def create_recall(
    name: str, request: Request,
    text: str = Form(...), tags: str = Form(""),
):
    p = _project_or_404(request, name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    r = request.app.state.memory.save_recall(
        p.id,
        Recall(project_id=p.id, text=text,
               tags=[t.strip() for t in tags.split(",") if t.strip()]),
    )
    return JSONResponse(r.model_dump(mode="json"))
```

- [ ] **Step 5: Run test (passes)**

Run: `pytest tests/test_router_memory.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add myorch/routers/memory.py myorch/templates/partials/ tests/test_router_memory.py
git commit -m "feat: memory router with Jinja-rendered fragments (XSS-safe) + FTS search"
```

---

### Task 7.5: Dev servers router

**Files:**
- Modify: `myorch/routers/devservers.py`
- Create: `myorch/templates/partials/devserver_tail.html`
- Test: `tests/test_router_devservers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router_devservers.py
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
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_router_devservers.py -v`
Expected: FAIL.

- [ ] **Step 3: Create tail partial template**

`myorch/templates/partials/devserver_tail.html`:
```html
{% for line in lines %}{{ line }}
{% endfor %}
```

(Single-statement template; Jinja auto-escapes each `{{ line }}`.)

- [ ] **Step 4: Implement `myorch/routers/devservers.py`**

```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/devservers", tags=["devservers"])


@router.post("/{name}/start")
async def start(name: str, request: Request):
    memory = request.app.state.memory
    dev_mgr = request.app.state.dev_mgr
    p = memory.get_project_by_name(name)
    if p is None or not p.dev_command:
        return JSONResponse({"error": "no dev_command set"}, status_code=400)
    dev_mgr.start(project_id=p.id, command=p.dev_command, cwd=p.path)
    return {"ok": True, "project": name}


@router.post("/{name}/stop")
async def stop(name: str, request: Request):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    request.app.state.dev_mgr.stop(p.id)
    return {"ok": True}


@router.get("/{name}/status")
async def status(name: str, request: Request):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"running": request.app.state.dev_mgr.is_running(p.id)}


@router.get("/{name}/tail")
async def tail(name: str, request: Request):
    memory = request.app.state.memory
    p = memory.get_project_by_name(name)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    lines = request.app.state.dev_mgr.tail(p.id)[-100:]
    accept = request.headers.get("accept", "")
    if "text/html" in accept or request.headers.get("hx-request") == "true":
        return request.app.state.templates.TemplateResponse(
            "partials/devserver_tail.html",
            {"request": request, "lines": lines},
        )
    return {"lines": lines}
```

- [ ] **Step 5: Run test (passes)**

Run: `pytest tests/test_router_devservers.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add myorch/routers/devservers.py myorch/templates/partials/devserver_tail.html
git add tests/test_router_devservers.py
git commit -m "feat: devservers router (start/stop/status/tail) with escaped HTML tail"
```

---

## Milestone 8 — Frontend wiring (xterm + paste + entry)

**Goal:** the workspace partial actually connects to the WebSocket, renders xterm, supports image paste — using safe DOM APIs (no `innerHTML` with untrusted content).

### Task 8.1: Static JS bundle

**Files:**
- Modify: `myorch/static/app.js` (replace placeholder)

- [ ] **Step 1: Replace `myorch/static/app.js`**

```javascript
window.attachTerminal = async function(responseText) {
  let body;
  try { body = JSON.parse(responseText); } catch (e) { return; }
  const sessionId = body.session_id;
  if (!sessionId) return;

  const el = document.getElementById('terminal');
  if (!el) return;
  // Safe clear: remove children rather than overwriting innerHTML.
  while (el.firstChild) el.removeChild(el.firstChild);
  const term = new Terminal({
    fontFamily: 'monospace', fontSize: 13, theme: { background: '#000' },
    convertEol: true,
  });
  term.open(el);

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/sessions/ws/${sessionId}`);
  ws.onmessage = (ev) => term.write(ev.data);
  ws.onclose = () => term.write('\r\n[disconnected]\r\n');

  window._activeSession = { ws, term, sessionId };
};

window.sendMsg = function() {
  const ta = document.getElementById('msg-input');
  const sess = window._activeSession;
  if (!ta || !sess || sess.ws.readyState !== 1) return;
  let text = ta.value;
  if (!text.endsWith('\n')) text += '\n';
  sess.ws.send(text);
  ta.value = '';
};

document.addEventListener('paste', async (e) => {
  const sess = window._activeSession;
  if (!sess) return;
  const items = e.clipboardData?.items || [];
  for (const item of items) {
    if (item.type?.startsWith('image/')) {
      e.preventDefault();
      const blob = item.getAsFile();
      if (!blob) continue;
      const fd = new FormData();
      fd.append('file', blob, 'paste.png');
      const r = await fetch(`/sessions/${sess.sessionId}/upload-image`, { method: 'POST', body: fd });
      if (r.ok) {
        const { path } = await r.json();
        const ta = document.getElementById('msg-input');
        if (ta) ta.value += `@${path} `;
      }
      break;
    }
  }
});

document.addEventListener('keydown', (e) => {
  if (e.target?.id === 'msg-input' && e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    window.sendMsg();
  }
});
```

- [ ] **Step 2: Smoke-run the app manually**

```bash
. .venv/bin/activate
uvicorn myorch.app:create_app --factory --host 127.0.0.1 --port 7000
```

Expected: server starts, no errors. Visit http://127.0.0.1:7000 — sidebar loads, "+ Scan" works.

Stop with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add myorch/static/app.js
git commit -m "feat: frontend JS wires xterm + paste + Enter-to-send (safe DOM clear)"
```

---

## Milestone 9 — Wiring & polish

### Task 9.1: Bootstrap (`mcp.json`, image cleanup)

**Files:**
- Create: `myorch/bootstrap.py`
- Modify: `myorch/app.py` (call bootstrap on create_app)
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bootstrap.py
import json
from pathlib import Path

from myorch.bootstrap import ensure_mcp_config
from myorch.config import Settings


def test_writes_mcp_config_pointing_at_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    s = Settings()
    ensure_mcp_config(s)
    cfg = json.loads(s.mcp_config_path.read_text())
    server = cfg["mcpServers"]["myorch-memory"]
    assert "myorch.mcp_server" in server["args"]
    assert server["env"]["MYORCH_DB"] == str(s.db_path)


def test_does_not_overwrite_existing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    s = Settings()
    s.mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
    s.mcp_config_path.write_text('{"customized": true}')
    ensure_mcp_config(s)
    assert s.mcp_config_path.read_text() == '{"customized": true}'
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_bootstrap.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `myorch/bootstrap.py`**

```python
import json
import shutil
import sys
import time

from myorch.config import Settings


def ensure_mcp_config(settings: Settings) -> None:
    path = settings.mcp_config_path
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "mcpServers": {
            "myorch-memory": {
                "command": sys.executable,
                "args": ["-m", "myorch.mcp_server"],
                "env": {
                    "MYORCH_DB": str(settings.db_path),
                    "MYORCH_PROJECT": "<set per-session by SessionManager>",
                },
            }
        }
    }
    path.write_text(json.dumps(config, indent=2))


def cleanup_orphan_images(settings: Settings, max_age_seconds: int = 24 * 3600) -> None:
    if not settings.tmp_dir.exists():
        return
    cutoff = time.time() - max_age_seconds
    for p in settings.tmp_dir.glob("*"):
        try:
            if p.stat().st_mtime < cutoff:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
        except OSError:
            pass
```

- [ ] **Step 4: Call from `create_app()` in `myorch/app.py`**

After `settings.tmp_dir.mkdir(...)`, add:

```python
    from myorch.bootstrap import cleanup_orphan_images, ensure_mcp_config
    ensure_mcp_config(settings)
    cleanup_orphan_images(settings)
```

- [ ] **Step 5: Run test (passes)**

Run: `pytest tests/test_bootstrap.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add myorch/bootstrap.py myorch/app.py tests/test_bootstrap.py
git commit -m "feat: bootstrap writes mcp.json and cleans up orphan tmp images"
```

---

### Task 9.2: SessionManager injects per-session MCP config

**Files:**
- Modify: `myorch/services/session_manager.py` (`open` writes per-session mcp.json; `_default_claude_argv` accepts `mcp_config_path`)
- Test: `tests/test_session_manager_mcp.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_manager_mcp.py
import json
from pathlib import Path

import pytest

from myorch.config import Settings
from myorch.db import connect, init_schema
from myorch.models import Project
from myorch.services.memory_service import MemoryService
from myorch.services.session_manager import SessionManager


def test_mcp_config_for_session_has_correct_project(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / ".myorch"))
    settings = Settings()
    conn = connect(settings.db_path)
    init_schema(conn)
    memory = MemoryService(conn)
    proj_dir = tmp_path / "alpha"
    proj_dir.mkdir()
    p = memory.upsert_project(Project(name="alpha", path=str(proj_dir)))
    captured: dict = {}

    def fake_factory(project, digest_path, resume_id, mcp_config_path):
        captured["mcp_path"] = mcp_config_path
        captured["project"] = project.name
        return ["cat"]

    mgr = SessionManager(memory=memory, settings=settings, claude_argv_factory=fake_factory)
    handle = mgr.open(project_id=p.id)
    try:
        cfg = json.loads(Path(captured["mcp_path"]).read_text())
        env = cfg["mcpServers"]["myorch-memory"]["env"]
        assert env["MYORCH_PROJECT"] == "alpha"
        assert env["MYORCH_DB"] == str(settings.db_path)
    finally:
        mgr.close(handle.session_id)
```

- [ ] **Step 2: Run test (fails)**

Run: `pytest tests/test_session_manager_mcp.py -v`
Expected: FAIL — `claude_argv_factory` does not yet receive `mcp_config_path`.

- [ ] **Step 3: Update `SessionManager.open` to materialize per-session mcp.json**

In `myorch/services/session_manager.py`, add to top:

```python
import json
import sys
```

Update `open()` — replace the section that builds `argv`:

```python
            # write per-session mcp.json (so MYORCH_PROJECT is correct)
            session_mcp_path = self.settings.data_dir / "run" / f"{project.name}.mcp.json"
            session_mcp_path.write_text(json.dumps({
                "mcpServers": {
                    "myorch-memory": {
                        "command": sys.executable,
                        "args": ["-m", "myorch.mcp_server"],
                        "env": {
                            "MYORCH_DB": str(self.settings.db_path),
                            "MYORCH_PROJECT": project.name,
                        },
                    }
                }
            }, indent=2))
            argv = self._claude_argv_factory(
                project=project, digest_path=digest_path,
                resume_id=project.last_session_id,
                mcp_config_path=session_mcp_path,
            )
```

Update `_default_claude_argv` signature:

```python
def _default_claude_argv(project, digest_path: Path, resume_id: str | None,
                         mcp_config_path: Path) -> list[str]:
    argv = ["claude"]
    if resume_id:
        argv.extend(["--resume", resume_id])
    argv.extend(["--mcp-config", str(mcp_config_path)])
    argv.extend(["--append-system-prompt", f"@{digest_path}"])
    return argv
```

Existing test fixtures use `claude_argv_factory=lambda **kw: ["cat"]` — they continue to work because `**kw` swallows the new argument.

- [ ] **Step 4: Run test (passes)**

Run: `pytest tests/test_session_manager_mcp.py -v`
Expected: 1 passed.

Re-run all session_manager tests:

Run: `pytest tests/test_session_manager_*.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add myorch/services/session_manager.py tests/test_session_manager_mcp.py
git commit -m "feat: SessionManager writes per-session mcp.json with MYORCH_PROJECT"
```

---

## Milestone 10 — End-to-end smoke + README

### Task 10.1: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

```markdown
# MyOrchestrator

Local web orchestrator for managing multiple Claude Code sessions across projects in `~/Documents/APPS/`. Single browser pane: project list, terminal per project, dev server controls, persistent memory in SQLite.

**No API key.** Uses your authenticated `claude` CLI subprocess (Pro/Max subscription).

## Requirements

- Python 3.11+
- `claude` CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code`)
- Linux/macOS

## Install

```bash
git clone <repo> && cd MyOrchestrator
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
. .venv/bin/activate
uvicorn myorch.app:create_app --factory --host 127.0.0.1 --port 7000
```

Open http://127.0.0.1:7000 — click "+ Scan" to discover your projects.

## Configuration

Environment variables (defaults shown):
- `MYORCH_APPS_ROOT=/home/$USER/Documents/APPS`
- `MYORCH_DATA_DIR=$HOME/.myorch`
- `MYORCH_TMP_DIR=/tmp/myorch`
- `MYORCH_HOST=127.0.0.1`
- `MYORCH_PORT=7000`

## Tests

```bash
pytest -v
```

## Architecture

See `docs/superpowers/specs/2026-05-05-myorchestrator-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with install, run, and config"
```

---

### Task 10.2: Manual end-to-end checklist

**Files:** none — verification only. Run through these steps with `claude` actually installed.

- [ ] **Step 1: Start the app**

```bash
. .venv/bin/activate
uvicorn myorch.app:create_app --factory --host 127.0.0.1 --port 7000
```

- [ ] **Step 2: Browser check — health**

Visit http://127.0.0.1:7000/health. Expected: JSON with `claude_cli: true`, `apps_root_exists: true`.

- [ ] **Step 3: Scan**

Click "+ Scan" in sidebar. Expected: list shows real projects from `<APPS_ROOT>/*`.

- [ ] **Step 4: Open a project**

Click on a project. Expected: workspace renders, terminal connects, you see the Claude Code prompt.

- [ ] **Step 5: Chat + memory**

Send: "Recuérdame que el dev server corre en :8000 — guárdalo como recall." Expected: Claude calls `save_recall` via MCP. Refresh memory panel — recall appears.

- [ ] **Step 6: Paste image**

Take a screenshot, Ctrl+V in the message area. Expected: `@/tmp/myorch/<id>/<uuid>.png ` appears in textarea. Send and confirm Claude sees the image.

- [ ] **Step 7: Dev server**

Click "▶ Start". Expected: tail shows dev server output. Click "⏹ Stop". Expected: tail stops growing, status reflects stopped.

- [ ] **Step 8: Close session**

`POST /sessions/<id>/close` via curl, or close the page (5 min idle triggers same flow). Expected: Claude generates summary, session marked closed in DB. Re-open the project: digest shows the summary you just wrote.

- [ ] **Step 9: Resume**

Re-open the same project. Expected: `claude --resume <last_session_id>` — Claude greets you with continuity.

- [ ] **Step 10: Final state**

```bash
git status   # should be clean
git log --oneline | head -20
```

If anything was wrong in the manual run, fix in a follow-up task before declaring V1 done.

---

## Self-review checklist (verified inline by author)

- [x] **Spec coverage:** every section of the spec maps to ≥1 task — projects (M3), sessions/PTY (M5), dev servers (M6), memory (M2), MCP (M4), web/UI (M7-8), edge cases (M5/M9), V1 must-haves (all milestones).
- [x] **Placeholders:** no TBD/TODO. Every code step contains the actual code; every test step contains real assertions.
- [x] **XSS hygiene:** all HTML rendering goes through Jinja2 templates with auto-escaping (decisions, recalls, search results, devserver tail). The frontend JS uses safe DOM clearing (no `innerHTML` with untrusted content) and `term.write()` (xterm sanitizes its own input).
- [x] **Type consistency:** model names (Project, Session, Decision, Recall, RecallHit, SessionBrief, SessionStatus) are stable. Method names (`upsert_project`, `update_project`, `save_decision`, `save_recall`, `save_summary`, `recall`, `list_decisions`, `list_recalls`, `list_recent_sessions`, `start_session`, `close_session`, `set_claude_session_id`, `get_session`, `get_project_by_id`, `get_project_by_name`, `list_projects`) consistent across tasks.
- [x] **Spike up front (M4 Task 4.0):** `claude_session_id` capture mechanism is researched before writing dependent code.
- [x] **TDD discipline:** every implementation task has a failing test → impl → passing test → commit cycle.

## Risks / things to watch during implementation

1. **`claude` flag stability.** `--mcp-config`, `--append-system-prompt`, `--resume` should all exist; if any is renamed, tasks 5.x and 9.2 need adjusting. Run `claude --help` at start of M4.
2. **PTY rendering quirks.** xterm.js may need `convertEol: true` or terminal dimensions tweaks if Claude's output looks broken. Adjust in Task 8.1 if needed.
3. **SQLite WAL on different filesystems.** WAL doesn't work over NFS. Local disk only — fine for `$HOME/.myorch/`.
4. **Subprocess group leakage on macOS.** `os.setsid` + `os.killpg` works on Linux. macOS works similarly but verify if user moves to mac.
5. **`cat`-as-claude stand-in tests.** They validate plumbing but not real Claude behavior — the manual checklist (10.2) is the real proof V1 works.
