"""Tiny in-process stand-in for the WeeChat embedded `weechat` module."""
import inspect
from collections import defaultdict
from typing import Any, Callable


_handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)
_modifiers: dict[str, Callable[..., str]] = {}
_buffers: dict[str, dict[str, Any]] = {}
_bar_items: dict[str, Callable[..., str]] = {}
_commands: dict[str, Callable[..., int]] = {}
_printed: list[tuple[str, str]] = []
_printed_y: list[tuple[str, int, str]] = []


def _resolve(callback):
    """If callback is a string (real-WeeChat convention), resolve it via the
    caller's module globals. Otherwise return as-is."""
    if not isinstance(callback, str):
        return callback
    for frame_info in inspect.stack()[1:]:
        cb = frame_info.frame.f_globals.get(callback)
        if callable(cb):
            return cb
    return callback


def reset() -> None:
    _handlers.clear()
    _modifiers.clear()
    _buffers.clear()
    _bar_items.clear()
    _commands.clear()
    _printed.clear()
    _printed_y.clear()


def register(name, author, version, license_, desc, shutdown_cb, charset):
    return 1


def hook_modifier(name, callback, data=""):
    _modifiers[name] = _resolve(callback)
    return f"modifier:{name}"


def hook_signal(name, callback, data=""):
    _handlers[name].append(_resolve(callback))
    return f"signal:{name}"


def hook_command(name, desc, args, args_desc, completion, callback, data=""):
    _commands[name] = _resolve(callback)
    return f"command:{name}"


def info_get_hashtable(info, table):
    if info == "irc_message_parse":
        message = table.get("message", "")
        out = {"tags": "", "command": "", "channel": "", "arguments": ""}
        rest = message
        if rest.startswith("@"):
            tags, _, rest = rest[1:].partition(" ")
            out["tags"] = tags
        if rest.startswith(":"):
            _, _, rest = rest.partition(" ")
        cmd, _, args = rest.partition(" ")
        out["command"] = cmd
        if cmd == "PRIVMSG":
            chan, _, msg = args.partition(" ")
            out["channel"] = chan
            out["arguments"] = msg.lstrip(":")
        return out
    return {}


def buffer_new(name, input_cb, input_data, close_cb, close_data):
    buf = {"name": name, "lines": [], "type": "free", "title": ""}
    _buffers[name] = buf
    return name


def buffer_search(plugin, name):
    return name if name in _buffers else ""


def buffer_set(buffer, prop, value):
    if buffer in _buffers:
        _buffers[buffer][prop] = value


def prnt(buffer, text):
    _printed.append((buffer, text))


def prnt_y(buffer, y, text):
    _printed_y.append((buffer, y, text))


def bar_item_new(name, callback, data=""):
    _bar_items[name] = _resolve(callback)
    return name


def bar_item_update(name):
    cb = _bar_items.get(name)
    if cb is None:
        return ""
    return cb(None, name, None)


def emit_signal(name: str, *args) -> None:
    for cb in _handlers.get(name, []):
        cb(*args)


def call_modifier(name: str, modifier_data: str, line: str) -> str:
    cb = _modifiers.get(name)
    if cb is None:
        return line
    return cb(None, name, modifier_data, line)


def call_command(name: str, *args) -> int:
    cb = _commands.get(name)
    if cb is None:
        return -1
    return cb(None, "buffer", " ".join(args))


def color(_name):
    return ""


def WEECHAT_RC_OK():
    return 0
