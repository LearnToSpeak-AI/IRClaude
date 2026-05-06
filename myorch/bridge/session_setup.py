import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from myorch.config import Settings
from myorch.digest import generate_digest
from myorch.models import Project
from myorch.services.memory_service import MemoryService


@dataclass
class SessionContext:
    project: Project
    session_id: int
    claude_uuid: str
    digest_path: Path
    mcp_config_path: Path


def _write_digest(project: Project, memory: MemoryService) -> Path:
    target_dir = Path(project.path) / ".myorch"
    target_dir.mkdir(parents=True, exist_ok=True)
    digest_path = target_dir / "CLAUDE.context.md"
    body = generate_digest(memory, project.id)
    digest_path.write_text(body, encoding="utf-8")
    return digest_path


def _write_mcp_config(project: Project, settings: Settings) -> Path:
    settings.run_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = settings.run_dir / f"{project.name}.mcp.json"
    payload = {
        "mcpServers": {
            "myorch": {
                "command": sys.executable,
                "args": ["-m", "myorch.mcp_server"],
                "env": {
                    "MYORCH_DATA_DIR": str(settings.data_dir),
                    "MYORCH_PROJECT_ID": str(project.id),
                },
            }
        }
    }
    mcp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return mcp_path


def prepare_session(
    project: Project,
    memory: MemoryService,
    settings: Settings,
) -> SessionContext:
    session = memory.start_session(project.id)
    claude_uuid = project.last_session_id or str(uuid.uuid4())
    if not project.last_session_id:
        memory.set_claude_session_id(session.id, claude_uuid)

    digest_path = _write_digest(project, memory)
    mcp_path = _write_mcp_config(project, settings)
    return SessionContext(
        project=project,
        session_id=session.id,
        claude_uuid=claude_uuid,
        digest_path=digest_path,
        mcp_config_path=mcp_path,
    )
