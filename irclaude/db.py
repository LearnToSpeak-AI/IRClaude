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
