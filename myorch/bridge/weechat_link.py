import os
import shutil
import subprocess
from pathlib import Path


def _from_weechat_d() -> Path | None:
    binary = shutil.which("weechat") or shutil.which("weechat-headless")
    if not binary:
        return None
    try:
        out = subprocess.run(
            [binary, "-d"], capture_output=True, text=True, timeout=4
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    return Path(out) / "python" / "autoload"


def _from_env() -> Path | None:
    raw = os.environ.get("WEECHAT_HOME")
    if not raw:
        return None
    return Path(raw) / "python" / "autoload"


def _from_xdg() -> Path | None:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "weechat" / "python" / "autoload"


def detect_weechat_plugin_dir() -> Path | None:
    for source in (_from_weechat_d, _from_env, _from_xdg):
        candidate = source()
        if candidate is not None and candidate.exists():
            return candidate
    return None


def repo_plugin_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "weechat_plugin" / "myorch.py"
