from pathlib import Path

import typer
from rich.console import Console

from myorch.bridge.ergo_fetch import download_ergo, parse_version_pin
from myorch.bridge.weechat_link import detect_weechat_plugin_dir, repo_plugin_path
from myorch.config import load_settings
from myorch.db import connect, init_schema
from myorch.services.memory_service import MemoryService
from myorch.services.project_registry import ProjectRegistry

app = typer.Typer(help="Local IRC orchestrator for multi-project Claude Code.")
console = Console()


def _write_default_config(path: Path, apps_root: Path, port: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"apps_root = \"{apps_root}\"\n"
        f"host = \"127.0.0.1\"\n"
        f"port = {port}\n"
    )
    path.write_text(body, encoding="utf-8")


@app.command()
def start() -> None:
    """Boot ergo + bridge in foreground."""
    console.print("[stub] start")


@app.command()
def stop() -> None:
    """Send save_summary to active sessions, terminate ergo + bridge."""
    console.print("[stub] stop")


@app.command()
def status() -> None:
    """Show component + session status."""
    console.print("[stub] status")


@app.command()
def setup() -> None:
    """First-run wizard: download ergo, scan projects, install plugin."""
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.bin_dir.mkdir(parents=True, exist_ok=True)
    pin = parse_version_pin(Path(__file__).resolve().parent.parent / "bin" / ".ergo-version")
    download_ergo(
        target_dir=settings.bin_dir,
        version=pin.version,
        expected_sha256=pin.sha256,
    )
    _write_default_config(
        settings.config_file, apps_root=settings.apps_root, port=settings.port
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    registry = ProjectRegistry(memory=mem, apps_root=settings.apps_root)
    found = registry.scan()
    console.print(f"Scanned [bold]{len(found)}[/bold] projects under {settings.apps_root}")

    pdir = detect_weechat_plugin_dir()
    if pdir is None:
        console.print("WeeChat plugin dir not detected — run [cyan]myorch setup-weechat[/cyan] manually.")
        return
    confirm = typer.prompt(f"Install WeeChat plugin into {pdir}? [y/N]", default="n")
    if confirm.lower().startswith("y"):
        target = pdir / "myorch.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(repo_plugin_path())
        console.print(f"Linked plugin to {target}")


@app.command(name="setup-weechat")
def setup_weechat() -> None:
    pdir = detect_weechat_plugin_dir()
    if pdir is None:
        console.print(
            "Could not detect WeeChat plugin dir. To install manually:\n"
            "  ln -s <repo>/weechat_plugin/myorch.py "
            "$WEECHAT_HOME/python/autoload/myorch.py"
        )
        return
    target = pdir / "myorch.py"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(repo_plugin_path())
    console.print(f"Linked plugin to {target}")


@app.command()
def scan() -> None:
    """Re-scan apps_root for projects."""
    console.print("[stub] scan")


@app.command(name="list")
def list_cmd() -> None:
    """List projects with last-activity preview."""
    console.print("[stub] list")


@app.command()
def search(query: str = typer.Argument(...)) -> None:
    """Full-text search across recalls + decisions."""
    console.print(f"[stub] search {query}")


@app.command()
def decisions(project: str = typer.Argument(...)) -> None:
    """List decisions for one project."""
    console.print(f"[stub] decisions {project}")


@app.command()
def logs() -> None:
    """Tail bridge log file."""
    console.print("[stub] logs")
