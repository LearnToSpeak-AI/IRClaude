from typer.testing import CliRunner

from irclaude.cli import app


runner = CliRunner()


def test_cli_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    for cmd in [
        "start", "stop", "status", "setup", "setup-weechat",
        "scan", "list", "search", "decisions", "logs",
    ]:
        assert cmd in out


def test_status_runs_without_error_for_stub():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0


def test_unknown_subcommand_returns_nonzero():
    result = runner.invoke(app, ["bogus"])
    assert result.exit_code != 0
