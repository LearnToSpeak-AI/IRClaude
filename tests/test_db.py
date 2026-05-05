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
