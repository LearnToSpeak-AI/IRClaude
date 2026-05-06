import sys
from pathlib import Path

import pytest


@pytest.fixture
def weechat_module(monkeypatch):
    sys.path.insert(0, str(Path(__file__).parent))
    import weechat_stub
    weechat_stub.reset()
    monkeypatch.setitem(sys.modules, "weechat", weechat_stub)
    sys.modules.pop("irclaude", None)
    plugin_dir = Path(__file__).resolve().parent.parent / "weechat_plugin"
    sys.path.insert(0, str(plugin_dir))
    import irclaude as plugin  # noqa: F401
    yield weechat_stub


def test_plugin_registers_irc_modifier(weechat_module):
    assert "irc_in2_privmsg" in weechat_module._modifiers


def test_modifier_passes_through_normal_privmsg(weechat_module):
    line = ":nick!user@host PRIVMSG #foo :hello"
    out = weechat_module.call_modifier("irc_in2_privmsg", "server.irc.irclaude", line)
    assert "hello" in out


def test_modifier_inspects_irclaude_kind_tag(weechat_module):
    line = "@+irclaude.kind=text :nick!u@h PRIVMSG #foo :hi"
    out = weechat_module.call_modifier("irc_in2_privmsg", "server.irc.irclaude", line)
    assert "hi" in out
