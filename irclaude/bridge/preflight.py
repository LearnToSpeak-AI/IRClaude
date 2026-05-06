"""Pre-flight checks for the IRClaude setup wizard."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClaudeStatus:
    installed: bool
    version: str | None
    auth_mode: str  # "subscription" | "api_key" | "none"
    hint: str | None


_INSTALL_HINT = (
    "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code/quickstart"
)
_LOGIN_HINT = (
    "No ~/.claude/ session found. Run `claude login` to authenticate with your "
    "Pro/Max subscription, or export ANTHROPIC_API_KEY to use API-key auth."
)


def check_claude(*, home: Path | None = None) -> ClaudeStatus:
    """Inspect whether the `claude` CLI is installed and how it will authenticate."""
    home = home or Path.home()
    binary = shutil.which("claude")
    if binary is None:
        return ClaudeStatus(
            installed=False,
            version=None,
            auth_mode="none",
            hint=_INSTALL_HINT,
        )
    version: str | None
    try:
        out = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=5
        )
        version = out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        version = None

    if os.environ.get("ANTHROPIC_API_KEY"):
        return ClaudeStatus(installed=True, version=version, auth_mode="api_key", hint=None)

    if (home / ".claude").exists():
        return ClaudeStatus(installed=True, version=version, auth_mode="subscription", hint=None)

    return ClaudeStatus(installed=True, version=version, auth_mode="none", hint=_LOGIN_HINT)
