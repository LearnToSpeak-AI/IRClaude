import os
import signal as _signal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from myorch.__about__ import __version__
from myorch.bridge.ergo_fetch import download_ergo, parse_version_pin
from myorch.bridge.weechat_link import detect_weechat_plugin_dir, repo_plugin_path
from myorch.config import load_settings
from myorch.db import connect, init_schema
from myorch.services.memory_service import MemoryService
from myorch.services.project_registry import ProjectRegistry

app = typer.Typer(help="Local IRC orchestrator for multi-project Claude Code.")
console = Console()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _launch_bridge_blocking(settings) -> None:
    import asyncio

    from myorch.bridge import Bridge
    from myorch.db import connect, init_schema
    from myorch.services.memory_service import MemoryService

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    bridge = Bridge(settings=settings, memory=mem)
    asyncio.run(bridge.run_with_signals())


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
    settings = load_settings()
    settings.run_dir.mkdir(parents=True, exist_ok=True)
    settings.pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        _launch_bridge_blocking(settings)
    except Exception:
        if settings.pid_file.exists():
            settings.pid_file.unlink()
        raise


@app.command()
def stop() -> None:
    """Stop a running myorch process via PID file."""
    settings = load_settings()
    if not settings.pid_file.exists():
        console.print("not running")
        return
    pid = int(settings.pid_file.read_text(encoding="utf-8").strip())
    os.kill(pid, _signal.SIGTERM)
    settings.pid_file.unlink()
    console.print(f"sent SIGTERM to {pid}")


@app.command()
def status() -> None:
    """Show component + session status."""
    settings = load_settings()
    table = Table(title="myorch status")
    table.add_column("component")
    table.add_column("state")
    if settings.pid_file.exists():
        pid = settings.pid_file.read_text(encoding="utf-8").strip()
        table.add_row("bridge", f"running (pid={pid})" if _pid_alive(int(pid)) else "stale pidfile")
    else:
        table.add_row("bridge", "not running")
    console.print(table)


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


@app.command(name="list")
def list_cmd() -> None:
    """List known projects with last-activity preview."""
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    table = Table(title="projects")
    table.add_column("name")
    table.add_column("path")
    table.add_column("last activity")
    for p in mem.list_projects():
        table.add_row(p.name, p.path, str(p.last_opened_at or "-"))
    console.print(table)


@app.command()
def search(query: str = typer.Argument(...)) -> None:
    """Full-text search across recalls + decisions, all projects."""
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    any_hit = False
    for proj in mem.list_projects():
        hits = mem.recall(proj.id, query, limit=10)
        if not hits:
            continue
        any_hit = True
        console.print(f"[bold]{proj.name}[/bold]")
        for h in hits:
            console.print(f"  - {h.snippet}")
    if not any_hit:
        console.print("(no matches)")


@app.command()
def decisions(project: str = typer.Argument(...)) -> None:
    settings = load_settings()
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    proj = mem.get_project_by_name(project)
    if proj is None:
        console.print(f"[red]unknown project[/red] {project}")
        raise typer.Exit(code=2)
    table = Table(title=f"decisions — {project}")
    table.add_column("title"); table.add_column("body")
    for d in mem.list_decisions(proj.id):
        table.add_row(d.title, d.body)
    console.print(table)


@app.command()
def scan() -> None:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    settings.apps_root.mkdir(parents=True, exist_ok=True)
    registry = ProjectRegistry(memory=mem, apps_root=settings.apps_root)
    found = registry.scan()
    console.print(f"scanned {len(found)} projects under {settings.apps_root}")
    for p in found:
        console.print(f"  - {p.name}")


@app.command()
def logs() -> None:
    """Tail bridge log file."""
    console.print("[stub] logs")


@app.command()
def version() -> None:
    """Print the myorch version."""
    console.print(__version__)
