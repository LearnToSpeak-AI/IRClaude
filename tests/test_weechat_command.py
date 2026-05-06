import sys
from pathlib import Path

import pytest


@pytest.fixture
def plugin(monkeypatch):
    sys.path.insert(0, str(Path(__file__).parent))
    import weechat_stub
    weechat_stub.reset()
    monkeypatch.setitem(sys.modules, "weechat", weechat_stub)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "weechat_plugin"))
    sys.modules.pop("irclaude", None)
    import irclaude
    return weechat_stub, irclaude


def test_command_registered(plugin):
    stub, _ = plugin
    assert "irclaude" in stub._commands


def test_projects_subcommand_sends_bang_to_claude(plugin):
    stub, _ = plugin
    stub.call_command("irclaude", "projects")
    sent = [t for buf, t in stub._printed if "PRIVMSG" in t and "!projects" in t]
    assert sent, stub._printed


def test_recall_subcommand_sends_bang_query(plugin):
    stub, _ = plugin
    stub.call_command("irclaude", "recall", "nginx")
    sent = [t for buf, t in stub._printed if "!recall nginx" in t]
    assert sent
