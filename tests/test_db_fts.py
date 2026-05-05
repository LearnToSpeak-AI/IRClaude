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
        ("Endpoint requires authorization header",),
    )
    rows = conn.execute(
        "SELECT origin FROM memory_fts WHERE memory_fts MATCH 'authorization'"
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
