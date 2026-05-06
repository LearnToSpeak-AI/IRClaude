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
    sys.modules.pop("myorch", None)
    import myorch
    return weechat_stub, myorch


def test_status_bar_item_is_registered(plugin):
    stub, _ = plugin
    assert "myorch_status" in stub._bar_items


def test_status_bar_format_includes_project_turn_agents(plugin):
    stub, mod = plugin
    line = (
        "@+myorch.kind=text;+myorch.session-id=abc;+myorch.turn-id=7 "
        ":nick!u@h PRIVMSG #foo :hi"
    )
    stub.call_modifier("irc_in2_privmsg", "server.irc.myorch", line)
    out = stub.bar_item_update("myorch_status")
    assert "proj=#foo" in out
    assert "turn=7" in out
    assert "agents=0" in out


def test_status_bar_increments_agent_count_on_join(plugin):
    stub, mod = plugin
    join_line = ":explore-1!u@h JOIN :#foo"
    stub.emit_signal("*,irc_in2_join", "server", "irc_in2_join", join_line)
    stub.call_modifier(
        "irc_in2_privmsg", "server.irc.myorch",
        "@+myorch.kind=agent-msg;+myorch.agent=explore-1 :explore-1!u@h PRIVMSG #foo :hi",
    )
    out = stub.bar_item_update("myorch_status")
    assert "agents=1" in out
