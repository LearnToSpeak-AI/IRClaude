import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
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
    return Path(__file__).resolve().parent.parent.parent / "weechat_plugin" / "irclaude.py"


def weechat_running() -> bool:
    """Return True if a weechat (TUI) process is currently active."""
    if shutil.which("pgrep") is None:
        return False
    try:
        out = subprocess.run(
            ["pgrep", "-x", "weechat"], capture_output=True, text=True, timeout=2
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


_MISSING_HEADLESS_HINT = (
    "weechat-headless not found on PATH (needed for auto-config). Install it:\n"
    "  Ubuntu/Debian:  sudo apt install weechat-headless\n"
    "  Fedora/RHEL:    sudo dnf install weechat-headless\n"
    "  Arch:           sudo pacman -S weechat (includes weechat-headless)\n"
    "  macOS:          brew install weechat\n"
    "Then rerun: irclaude setup-weechat"
)


@dataclass(frozen=True)
class PackageInstallPlan:
    """A resolved install command for a given OS package manager."""
    manager: str
    command: tuple[str, ...]


def detect_weechat_install_plan() -> PackageInstallPlan | None:
    """Best-effort detection of how to install weechat-headless on this OS.

    Returns None if no supported package manager is found.
    """
    if platform.system() == "Darwin":
        if shutil.which("brew"):
            return PackageInstallPlan("brew", ("brew", "install", "weechat"))
        return None
    if shutil.which("apt-get"):
        return PackageInstallPlan(
            "apt", ("sudo", "apt-get", "install", "-y", "weechat-headless")
        )
    if shutil.which("dnf"):
        return PackageInstallPlan(
            "dnf", ("sudo", "dnf", "install", "-y", "weechat-headless")
        )
    if shutil.which("pacman"):
        return PackageInstallPlan(
            "pacman", ("sudo", "pacman", "-S", "--noconfirm", "weechat")
        )
    return None


def install_weechat_headless(plan: PackageInstallPlan) -> tuple[bool, str]:
    """Run the package-manager command interactively so the user sees sudo prompts
    and progress output. Returns (ok, message).
    """
    try:
        rc = subprocess.run(list(plan.command), check=False, timeout=600).returncode
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"install command failed: {exc}"
    if rc != 0:
        return False, f"install via {plan.manager} exited with code {rc}"
    return True, f"installed weechat-headless via {plan.manager}"


def add_weechat_server_via_headless(
    name: str,
    host: str,
    port: int,
    *,
    binary: str | None = None,
) -> tuple[bool, str]:
    """Add a server entry (no-TLS, autoconnect) to WeeChat's irc.conf via weechat-headless.

    Idempotent: if the server already exists, WeeChat reports an error which we treat as
    success so reruns of `irclaude setup` don't fail.

    Returns (ok, message). `ok` is False only when weechat-headless is missing or the
    subprocess invocation itself errored. When the binary is missing, the message
    includes per-OS install commands.
    """
    bin_path = binary or shutil.which("weechat-headless")
    if bin_path is None:
        return False, _MISSING_HEADLESS_HINT
    cmd = [
        bin_path,
        "--run-command",
        f"/server add {name} {host}/{port} -notls -autoconnect;/save;/quit",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"weechat-headless failed: {exc}"
    combined = (out.stdout + out.stderr).lower()
    if "already exists" in combined or "already used" in combined:
        return True, f"server '{name}' was already configured (no change)"
    if out.returncode != 0:
        return False, (
            f"weechat-headless exit={out.returncode} "
            f"stderr={(out.stderr or out.stdout).strip()[:200]}"
        )
    return True, f"server '{name}' added to WeeChat config (host={host} port={port}, no-TLS)"
