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
