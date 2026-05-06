import typer
from rich.console import Console

app = typer.Typer(help="Local IRC orchestrator for multi-project Claude Code.")
console = Console()


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
    """Interactive first-run wizard."""
    console.print("[stub] setup")


@app.command(name="setup-weechat")
def setup_weechat() -> None:
    """Detect and link the WeeChat plugin."""
    console.print("[stub] setup-weechat")


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
