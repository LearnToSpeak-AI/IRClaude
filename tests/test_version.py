from typer.testing import CliRunner

from irclaude.__about__ import __version__
from irclaude.cli import app


runner = CliRunner()


def test_version_constant_is_2_0_0():
    assert __version__ == "2.0.0"


def test_version_command_prints_constant():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "2.0.0" in result.stdout
