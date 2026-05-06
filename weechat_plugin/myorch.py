"""WeeChat plugin for myorch — render IRCv3 +myorch.* tagged events."""

import weechat


PLUGIN_NAME = "myorch"
PLUGIN_VERSION = "2.0.0"


_state: dict[str, object] = {
    "code_buffer_index": 0,
}


def _parse_tags(raw_tags: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for piece in raw_tags.split(";"):
        if not piece:
            continue
        if "=" in piece:
            k, v = piece.split("=", 1)
            out[k] = v
        else:
            out[piece] = ""
    return out


def cb_modifier_privmsg(data, modifier, modifier_data, line):
    parsed = weechat.info_get_hashtable("irc_message_parse", {"message": line})
    tags = _parse_tags(parsed.get("tags", ""))
    kind = tags.get("+myorch.kind") or tags.get("myorch.kind")
    if not kind:
        return line
    if kind == "code":
        return line
    return line


def shutdown_cb():
    return weechat.WEECHAT_RC_OK()


weechat.register(
    PLUGIN_NAME,
    "ipena",
    PLUGIN_VERSION,
    "MIT",
    "MyOrchestrator IRC bridge plugin",
    "shutdown_cb",
    "",
)
weechat.hook_modifier("irc_in2_privmsg", cb_modifier_privmsg, "")
