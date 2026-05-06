import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from irclaude.bridge.claude_runner import _claude_conversation_exists
from irclaude.config import Settings
from irclaude.digest import generate_digest
from irclaude.models import Project
from irclaude.services.memory_service import MemoryService


@dataclass
class SessionContext:
    project: Project
    session_id: int
    claude_uuid: str
    digest_path: Path
    mcp_config_path: Path
    is_resume: bool = False


def _write_digest(project: Project, memory: MemoryService) -> Path:
    target_dir = Path(project.path) / ".irclaude"
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
            "irclaude": {
                "command": sys.executable,
                "args": ["-m", "irclaude.mcp_server"],
                "env": {
                    "IRCLAUDE_DATA_DIR": str(settings.data_dir),
                    "IRCLAUDE_PROJECT_ID": str(project.id),
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
    candidate = project.last_session_id
    is_resume = bool(candidate) and _claude_conversation_exists(candidate)
    claude_uuid = candidate if is_resume else str(uuid.uuid4())
    memory.set_claude_session_id(session.id, claude_uuid)

    digest_path = _write_digest(project, memory)
    mcp_path = _write_mcp_config(project, settings)
    return SessionContext(
        project=project,
        session_id=session.id,
        claude_uuid=claude_uuid,
        digest_path=digest_path,
        mcp_config_path=mcp_path,
        is_resume=is_resume,
    )
