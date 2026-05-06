import os
import shutil
import signal as _signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from irclaude.__about__ import __version__
from irclaude.bridge.ergo_config import generate_ergo_config
from irclaude.bridge.ergo_fetch import download_ergo, parse_version_pin
from irclaude.bridge.preflight import check_claude
from irclaude.bridge.server import ErgoServer
from irclaude.bridge.weechat_link import (
    add_weechat_server_via_headless,
    detect_weechat_install_plan,
    detect_weechat_plugin_dir,
    install_weechat_headless,
    repo_plugin_path,
    weechat_running,
)
from irclaude.config import load_settings
from irclaude.db import connect, init_schema
from irclaude.services.memory_service import MemoryService
from irclaude.services.project_registry import ProjectRegistry

app = typer.Typer(help="Local IRC orchestrator for multi-project Claude Code.")
console = Console()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


async def _wait_for_port(host: str, port: int, deadline_s: float = 5.0) -> bool:
    import asyncio

    loop = asyncio.get_event_loop()
    end = loop.time() + deadline_s
    while loop.time() < end:
        try:
            r, w = await asyncio.open_connection(host, port)
            w.close()
            await w.wait_closed()
            return True
        except OSError:
            await asyncio.sleep(0.1)
    return False


async def _run_ergo_and_bridge(settings) -> None:
    import asyncio

    from irclaude.bridge import Bridge

    if not settings.ergo_config.exists():
        raise RuntimeError(
            f"ergo config not found at {settings.ergo_config} — run `irclaude setup` first"
        )
    if not settings.ergo_binary.exists():
        raise RuntimeError(
            f"ergo binary not found at {settings.ergo_binary} — run `irclaude setup` first"
        )

    server = ErgoServer(
        binary_path=settings.ergo_binary,
        config_path=settings.ergo_config,
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    bridge = Bridge(settings=settings, memory=mem)

    console.print(f"[cyan]starting ergo[/cyan] at {settings.host}:{settings.port}")
    await server.start()
    if not await _wait_for_port(settings.host, settings.port, deadline_s=5.0):
        await server.stop()
        raise RuntimeError(
            f"ergo did not accept connections on {settings.host}:{settings.port} within 5s"
        )
    console.print("[green]ergo ready[/green] — starting bridge")
    try:
        await bridge.run_with_signals()
    finally:
        console.print("[cyan]stopping ergo[/cyan]")
        await server.stop()


def _launch_bridge_blocking(settings) -> None:
    import asyncio

    asyncio.run(_run_ergo_and_bridge(settings))


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
    """Stop a running irclaude process via PID file."""
    settings = load_settings()
    if not settings.pid_file.exists():
        console.print("not running")
        return
    pid = int(settings.pid_file.read_text(encoding="utf-8").strip())
    os.kill(pid, _signal.SIGTERM)
    settings.pid_file.unlink()
    console.print(f"sent SIGTERM to {pid}")


@app.command()
def up() -> None:
    """Boot ergo + bridge in the background and open WeeChat in the same terminal."""
    settings = load_settings()

    if not settings.ergo_binary.exists():
        console.print(
            "[red]ergo binary not found[/red] — run "
            "[cyan]irclaude setup[/cyan] first."
        )
        raise typer.Exit(code=1)
    if shutil.which("weechat") is None:
        console.print(
            "[red]weechat not on PATH[/red] — install it "
            "(e.g. [cyan]sudo apt install weechat[/cyan])."
        )
        raise typer.Exit(code=1)

    bridge_was_running = (
        settings.pid_file.exists()
        and _pid_alive(int(settings.pid_file.read_text(encoding="utf-8").strip()))
    )
    if bridge_was_running:
        pid = settings.pid_file.read_text(encoding="utf-8").strip()
        console.print(f"[green]✓[/green] bridge already running (pid={pid})")
    else:
        if settings.pid_file.exists():
            settings.pid_file.unlink()
        settings.run_dir.mkdir(parents=True, exist_ok=True)
        log_file = settings.run_dir / "bridge.log"
        with open(log_file, "ab") as fh:
            proc = subprocess.Popen(
                [sys.executable, "-m", "irclaude", "start"],
                stdout=fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        deadline = time.monotonic() + 10.0
        ready = False
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(
                    (settings.host, settings.port), timeout=0.25
                ):
                    ready = True
                    break
            except OSError:
                time.sleep(0.2)
        if not ready:
            try:
                os.kill(proc.pid, _signal.SIGTERM)
            except OSError:
                pass
            console.print(
                f"[red]ergo did not become ready in 10s[/red] — see {log_file}"
            )
            raise typer.Exit(code=1)
        console.print(f"[green]✓[/green] bridge started (logs: {log_file})")

    console.print("[cyan]Launching WeeChat...[/cyan]")
    rc = subprocess.run(["weechat"]).returncode
    console.print(f"[cyan]WeeChat exited (code={rc}).[/cyan]")

    if not bridge_was_running and settings.pid_file.exists():
        confirm = typer.prompt("Stop ergo + bridge too? [Y/n]", default="y")
        if confirm.lower().startswith("y"):
            try:
                pid = int(settings.pid_file.read_text(encoding="utf-8").strip())
                os.kill(pid, _signal.SIGTERM)
                console.print(f"[green]✓[/green] sent SIGTERM to {pid}")
            except (OSError, ValueError):
                pass
            try:
                settings.pid_file.unlink()
            except OSError:
                pass


@app.command()
def status() -> None:
    """Show component + session status."""
    settings = load_settings()
    table = Table(title="irclaude status")
    table.add_column("component")
    table.add_column("state")
    if settings.pid_file.exists():
        pid = settings.pid_file.read_text(encoding="utf-8").strip()
        table.add_row("bridge", f"running (pid={pid})" if _pid_alive(int(pid)) else "stale pidfile")
    else:
        table.add_row("bridge", "not running")
    console.print(table)


_APPS_ROOT_CANDIDATES = (
    "Documents/APPS",
    "Documents/projects",
    "Documents/code",
    "code",
    "dev",
    "src",
    "workspace",
    "projects",
)


def _suggest_apps_root(default: Path) -> Path:
    home = Path.home()
    for rel in _APPS_ROOT_CANDIDATES:
        candidate = home / rel
        if candidate.exists() and any(child.is_dir() for child in candidate.iterdir()):
            return candidate
    return default


def _prompt_for_apps_root(default: Path) -> Path:
    suggested = _suggest_apps_root(default)
    raw = typer.prompt(
        "Where are your project folders located?",
        default=str(suggested),
    )
    return Path(raw).expanduser().resolve()


def _print_claude_status() -> None:
    status = check_claude()
    if not status.installed:
        console.print("[yellow]✗ claude CLI not found on PATH[/yellow]")
        console.print(f"  {status.hint}")
        return
    label = status.version or "(version unknown)"
    if status.auth_mode == "subscription":
        console.print(f"[green]✓[/green] claude CLI {label} — using Pro/Max subscription")
    elif status.auth_mode == "api_key":
        console.print(f"[green]✓[/green] claude CLI {label} — using ANTHROPIC_API_KEY")
    else:
        console.print(f"[yellow]✗[/yellow] claude CLI {label} found but not authenticated")
        console.print(f"  {status.hint}")


@app.command()
def doctor() -> None:
    """Check that prerequisites (Claude Code CLI, auth) are satisfied."""
    _print_claude_status()


@app.command()
def setup() -> None:
    """First-run wizard: verify prerequisites, download ergo, scan projects, configure WeeChat."""
    console.print("[bold]Pre-flight checks[/bold]")
    _print_claude_status()
    console.print()

    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.bin_dir.mkdir(parents=True, exist_ok=True)
    pin = parse_version_pin(Path(__file__).resolve().parent.parent / "bin" / ".ergo-version")
    download_ergo(
        target_dir=settings.bin_dir,
        version=pin.version,
        expected_sha256=pin.sha256,
    )

    if "IRCLAUDE_APPS_ROOT" not in os.environ:
        chosen = _prompt_for_apps_root(settings.apps_root)
        if chosen != settings.apps_root:
            settings = settings.model_copy(update={"apps_root": chosen})

    settings.etc_dir.mkdir(parents=True, exist_ok=True)
    settings.ergo_config.write_text(
        generate_ergo_config(
            host=settings.host,
            port=settings.port,
            datastore_path=str(settings.data_dir / "ergo.db"),
            binary_path=settings.ergo_binary,
        ),
        encoding="utf-8",
    )
    console.print(f"Wrote ergo config to {settings.ergo_config}")

    import subprocess
    initdb = subprocess.run(
        [str(settings.ergo_binary), "initdb", "--conf", str(settings.ergo_config), "--quiet"],
        capture_output=True,
        text=True,
    )
    if initdb.returncode != 0 and "already exists" not in (initdb.stderr + initdb.stdout):
        raise RuntimeError(f"ergo initdb failed: {initdb.stderr or initdb.stdout}")
    console.print("Initialized ergo datastore")

    _write_default_config(
        settings.config_file, apps_root=settings.apps_root, port=settings.port
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.apps_root.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    registry = ProjectRegistry(memory=mem, apps_root=settings.apps_root)
    found = registry.scan()
    console.print(f"Scanned [bold]{len(found)}[/bold] projects under {settings.apps_root}")
    if found:
        for p in found:
            console.print(f"  - {p.name}")

    pdir = detect_weechat_plugin_dir()
    if pdir is None:
        console.print(
            "[yellow]WeeChat plugin dir not detected[/yellow] — run "
            "[cyan]irclaude setup-weechat[/cyan] after installing WeeChat."
        )
        _print_next_steps(settings, weechat_configured=False)
        return

    confirm = typer.prompt(f"Install WeeChat plugin into {pdir}? [Y/n]", default="y")
    if confirm.lower().startswith("y"):
        target = pdir / "irclaude.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(repo_plugin_path())
        console.print(f"[green]✓[/green] Linked plugin to {target}")

    server_configured = _configure_weechat_server(settings)
    _print_next_steps(settings, weechat_configured=server_configured)


def _configure_weechat_server(settings) -> bool:
    """Prompt + auto-add the irclaude server to WeeChat. Installs weechat-headless
    on demand if the user agrees. Returns True iff the server entry is in irc.conf.
    """
    if weechat_running():
        console.print(
            "[yellow]WeeChat is currently running[/yellow] — skipping auto server config "
            "(close WeeChat first, then rerun [cyan]irclaude setup-weechat[/cyan])."
        )
        return False
    confirm = typer.prompt(
        f"Auto-configure WeeChat server '{settings.host}/{settings.port}' (no-TLS)? [Y/n]",
        default="y",
    )
    if not confirm.lower().startswith("y"):
        return False

    ok, msg = add_weechat_server_via_headless(
        "irclaude", settings.host, settings.port
    )
    if ok:
        console.print(f"[green]✓[/green] {msg}")
        return True

    if "not found on PATH" in msg:
        plan = detect_weechat_install_plan()
        if plan is not None:
            cmd_str = " ".join(plan.command)
            console.print(f"[yellow]weechat-headless not installed[/yellow]")
            confirm = typer.prompt(
                f"Run '{cmd_str}' now? [Y/n]", default="y"
            )
            if confirm.lower().startswith("y"):
                inst_ok, inst_msg = install_weechat_headless(plan)
                if inst_ok:
                    console.print(f"[green]✓[/green] {inst_msg}")
                    ok, msg = add_weechat_server_via_headless(
                        "irclaude", settings.host, settings.port
                    )
                    tag = "[green]✓[/green]" if ok else "[yellow]✗[/yellow]"
                    console.print(f"{tag} {msg}")
                    return ok
                console.print(f"[yellow]✗[/yellow] {inst_msg}")
                return False
        # No plan or user declined — fall through to printing the manual hint.

    console.print(f"[yellow]✗[/yellow] {msg}")
    return False


def _print_next_steps(settings, *, weechat_configured: bool) -> None:
    console.print()
    console.print("[bold]Next steps[/bold]")
    if weechat_configured:
        console.print(
            f"  1. Run [cyan]irclaude up[/cyan] — boots ergo + bridge in the "
            "background and opens WeeChat (autoloads plugin, autoconnects)."
        )
        console.print(f"  2. In WeeChat, run [cyan]/join #yourproject[/cyan]")
        console.print(
            "  (Or use [cyan]irclaude start[/cyan] in one terminal + "
            "[cyan]weechat[/cyan] in another if you prefer separate logs.)"
        )
    else:
        console.print(f"  1. Run [cyan]irclaude start[/cyan] to launch ergo + bridge")
        console.print(f"  2. In another terminal, run [cyan]weechat[/cyan]")
        console.print(
            f"  3. In WeeChat, run "
            f"[cyan]/server add irclaude {settings.host}/{settings.port} -notls -autoconnect[/cyan]"
            f" then [cyan]/connect irclaude[/cyan]"
        )
        console.print(
            "     (the plugin already autoloads from "
            "[cyan]~/.local/share/weechat/python/autoload/[/cyan])"
        )


@app.command(name="setup-weechat")
def setup_weechat() -> None:
    """Install the WeeChat plugin and (optionally) configure the irclaude server."""
    settings = load_settings()
    pdir = detect_weechat_plugin_dir()
    if pdir is None:
        console.print(
            "Could not detect WeeChat plugin dir. To install manually:\n"
            "  ln -s <repo>/weechat_plugin/irclaude.py "
            "$WEECHAT_HOME/python/autoload/irclaude.py"
        )
        return
    target = pdir / "irclaude.py"
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(repo_plugin_path())
    console.print(f"[green]✓[/green] Linked plugin to {target}")

    _configure_weechat_server(settings)


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
    """Print the irclaude version."""
    console.print(__version__)
