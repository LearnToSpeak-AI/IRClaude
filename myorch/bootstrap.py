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
