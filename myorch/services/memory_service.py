import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from myorch.models import Project, Session, SessionBrief, SessionStatus


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
               WHERE project_id=? ORDER BY started_at DESC, id DESC LIMIT ?""",
            (project_id, limit),
        ).fetchall()
        return [
            SessionBrief(
                id=r["id"], started_at=r["started_at"], ended_at=r["ended_at"],
                summary=r["summary"], status=SessionStatus(r["status"]),
            )
            for r in rows
        ]
