import pytest

from irclaude.bridge.core import Bridge


def test_bang_command_routes_to_control_handler():
    handled: list[tuple[str, str]] = []

    bridge = Bridge.__new__(Bridge)
    bridge._control_handlers = {
        "projects": lambda chan, args: handled.append((chan, "projects")),
        "recall": lambda chan, args: handled.append((chan, f"recall {args}")),
    }
    assert Bridge._handle_control(bridge, "#foo", "!projects") is True
    assert Bridge._handle_control(bridge, "#foo", "!recall nginx") is True
    assert handled == [("#foo", "projects"), ("#foo", "recall nginx")]


def test_non_bang_text_is_not_a_control_command():
    bridge = Bridge.__new__(Bridge)
    bridge._control_handlers = {
        "projects": lambda c, a: None,
    }
    assert Bridge._handle_control(bridge, "#foo", "regular message") is False
