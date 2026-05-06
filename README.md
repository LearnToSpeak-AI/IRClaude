# MyOrchestrator

Local IRC-driven orchestrator for multi-project Claude Code sessions.

<!-- TODO: record after first manual e2e -->
[Asciinema demo placeholder — link added once recording exists.]

## What is this

`myorch` lets you talk to Claude Code from your favorite chat client (WeeChat),
one IRC channel per project, without running a web server, without an API key,
and without losing context across sessions. Memory persists in SQLite.

## Why

- IRC is a perfect transport for "human + agents in a channel."
- WeeChat is uniquely scriptable — code blocks render in free buffers, agents
  appear as nicks, status bar shows session metadata.
- ergo gives us modern IRCv3 (message-tags, BATCH, draft/multiline) on a
  single Go binary.

## Architecture

```
WeeChat -> ergo (127.0.0.1:6667) -> Python bridge -> claude -p (subprocess)
                                            |
                                            +-> SQLite memory + MCP server
```

## Requirements

- Python 3.11+
- WeeChat 4.3+ (for rich rendering; any IRC client works for plain chat)
- Linux or macOS (Windows untested in V2)

## Install

```sh
pipx install myorch
myorch setup
```

`myorch setup` downloads the pinned ergo binary, scans `MYORCH_APPS_ROOT`,
writes `~/.config/myorch/config.toml`, and offers to install the WeeChat
plugin.

## Daily use

```sh
myorch start
# in another terminal:
weechat
# /server add myorch 127.0.0.1/6667
# /connect myorch
# /join #yourproject
```

## Configuration

| Env var              | Default                          | Meaning            |
|----------------------|----------------------------------|--------------------|
| `MYORCH_APPS_ROOT`   | `~/projects`                     | Where to scan      |
| `MYORCH_DATA_DIR`    | `$XDG_DATA_HOME/myorch`          | DB + ergo binary   |
| `MYORCH_CONFIG_FILE` | `$XDG_CONFIG_HOME/myorch/config.toml` | TOML overrides |
| `MYORCH_PORT`        | `6667`                           | ergo bind port     |

`config.toml` schema:

```toml
apps_root = "/srv/projects"
host = "127.0.0.1"
port = 6667
```

## FAQ

**Why no API key?** `myorch` shells out to the `claude` CLI on every turn,
using your existing Claude Code subscription. There is no `ANTHROPIC_API_KEY`
in the codebase or runtime — by design.

**Without the WeeChat plugin?** Chat still works on any IRC client. Code
blocks appear as raw `BATCH` lines (visible, unstyled). Agents still show up
as JOIN/PART nicks.

## Contributing

PRs welcome. Run `pytest -q` (requires `ergo` on `$PATH` for integration
tests; install via `myorch setup` once or `apt install ergo`/`brew install
ergo`).

## License

MIT — see `LICENSE`.
