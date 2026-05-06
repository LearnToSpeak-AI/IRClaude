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
    import irclaude as plugin
    return weechat_stub, plugin


SERVER = "irclaude"


def _send_batch(stub, channel: str, lang: str, lines: list[str]) -> None:
    # Real WeeChat creates a buffer named <server>.<channel> when the user
    # joins; the plugin looks it up via buffer_search to print the code marker
    # there.
    stub.buffer_new(f"{SERVER}.{channel}", "", "", "", "")
    open_line = (
        f"@batch=ABC;+irclaude.kind=code;+irclaude.codeblock={lang} "
        f":server.local BATCH +ABC draft/multiline {channel}"
    )
    stub.call_modifier("irc_in2_privmsg", SERVER, open_line)
    for line in lines:
        wire = f"@batch=ABC :n!u@h PRIVMSG {channel} :{line}"
        stub.call_modifier("irc_in2_privmsg", SERVER, wire)
    close_line = ":server.local BATCH -ABC"
    stub.call_modifier("irc_in2_privmsg", SERVER, close_line)


def test_codeblock_opens_free_buffer_with_lines(plugin):
    stub, _ = plugin
    _send_batch(stub, "#foo", "python", ["def hi():", "    return 42"])
    target = "code:#foo:1"
    assert target in stub._buffers
    body = [t for buf, _, t in stub._printed_y if buf == target]
    assert any("def hi():" in line for line in body)
    assert any("return 42" in line for line in body)


def test_codeblock_leaves_marker_in_main_channel(plugin):
    stub, _ = plugin
    _send_batch(stub, "#foo", "python", ["x = 1"])
    main_lines = [t for buf, t in stub._printed if buf == f"{SERVER}.#foo"]
    assert any("code" in t.lower() and "code:#foo:1" in t for t in main_lines)


def test_two_codeblocks_get_distinct_buffer_indices(plugin):
    stub, _ = plugin
    _send_batch(stub, "#foo", "python", ["a = 1"])
    _send_batch(stub, "#foo", "python", ["b = 2"])
    assert "code:#foo:1" in stub._buffers
    assert "code:#foo:2" in stub._buffers


def test_ergo_style_batch_close_with_leading_colon(plugin):
    """Regression: ergo emits 'BATCH :-<id>' (IRC trailing-parameter syntax).

    The plugin must strip the leading ':' before recognising close.
    """
    stub, _ = plugin
    stub.buffer_new(f"{SERVER}.#foo", "", "", "", "")
    open_line = (
        "@batch=Z;+irclaude.kind=code;+irclaude.codeblock=python "
        ":server.local BATCH +Z draft/multiline :#foo"
    )
    stub.call_modifier("irc_in2_privmsg", SERVER, open_line)
    inner = "@batch=Z :n!u@h PRIVMSG #foo :z = 99"
    stub.call_modifier("irc_in2_privmsg", SERVER, inner)
    close_line = ":server.local BATCH :-Z"
    stub.call_modifier("irc_in2_privmsg", SERVER, close_line)
    # Code buffer should exist and the marker should land in the channel buffer.
    assert "code:#foo:1" in stub._buffers
    main_lines = [t for buf, t in stub._printed if buf == f"{SERVER}.#foo"]
    assert any("code:#foo:1" in t for t in main_lines)
