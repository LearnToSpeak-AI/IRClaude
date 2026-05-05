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
