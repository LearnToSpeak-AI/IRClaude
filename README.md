# IRClaude

> Talk to Claude Code from IRC. One channel per project, persistent memory, no API key required.

`irclaude` boots a local [ergo](https://github.com/ergochat/ergo) IRCv3 server,
bridges it to the `claude` CLI, and ships a WeeChat plugin that renders
code blocks, agents, and session metadata as first-class IRC primitives.

```
WeeChat ── ergo (127.0.0.1:6667) ── Python bridge ── claude -p
                                                       │
                                                       └─ SQLite memory + MCP
```

- **One channel per project.** `#myapp`, `#that-side-thing`, `#whatever`.
  Each maps to a folder under your `apps_root`.
- **Sub-agents as nicks.** When Claude spawns an agent, it JOINs the channel
  as a separate user. PART when it's done.
- **Memory across sessions.** Decisions, recalls, and per-turn context live in
  SQLite, exposed to Claude via an MCP server.
- **Your subscription, not your wallet.** `irclaude` shells out to the `claude`
  CLI, so it uses your Pro/Max session by default. `ANTHROPIC_API_KEY` is
  supported for users who prefer pay-as-you-go.

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/quickstart)
  (`claude login` once, or `export ANTHROPIC_API_KEY=...`)
- WeeChat 4.3+ for rich rendering — any IRC client works for plain chat
- Linux or macOS (Windows untested)

## Install

```sh
git clone https://github.com/LearnToSpeak-AI/IRClaude.git
cd IRClaude
make install         # equivalent to: pipx install -e .
irclaude setup
```

`irclaude setup` is the wizard:

1. Verifies the `claude` CLI is installed and authenticated.
2. Downloads the pinned ergo binary (sha256-verified) into `$XDG_DATA_HOME/irclaude/bin/`.
3. Asks where your project folders live (e.g. `~/Documents/APPS`).
4. Scans that folder and registers each subdirectory as a project (one IRC channel per project).
5. Symlinks the WeeChat plugin into your WeeChat plugin dir.
6. Adds an `irclaude` server entry to WeeChat (`127.0.0.1/6667`, **no TLS**, autoconnect) — automatically, via `weechat-headless`. Skipped if WeeChat is currently running.

If anything looks off later, `irclaude doctor` re-runs the prerequisite checks
and `irclaude setup-weechat` re-runs just the WeeChat steps.

## Daily use

The fast path is `irclaude up` — it boots ergo + bridge in the background
and opens WeeChat in the same terminal. The plugin autoloads, the server
autoconnects, you just `/join`:

```sh
irclaude up                # one terminal: backgrounded bridge + foreground WeeChat
# /join #yourproject
# type a message — Claude responds in the channel
# /quit when done
```

When you `/quit` WeeChat, `irclaude up` asks whether to stop the bridge too.

If you prefer split terminals (e.g. to watch bridge logs live):

```sh
irclaude start             # foreground: ergo + bridge, Ctrl+C to stop
# in another terminal:
weechat                    # auto-loads plugin, auto-connects to irclaude
# /join #yourproject
```

To stop a backgrounded run started elsewhere, `irclaude stop` reads the PID
file and sends SIGTERM.

## Authentication: subscription vs API key

`irclaude` does not handle auth itself — it inherits whatever the local
`claude` CLI is configured for:

- **Pro/Max subscription (default):** run `claude login` once. `irclaude` will
  detect `~/.claude/` and report `using Pro/Max subscription` in `irclaude doctor`.
- **API key:** `export ANTHROPIC_API_KEY=sk-...` before `irclaude start`. The
  `claude` CLI prefers the env var over the session, so every turn is billed
  to your API account. `irclaude doctor` will report `using ANTHROPIC_API_KEY`.

Switching modes is just a matter of setting/unsetting the env var. Nothing in
`irclaude` stores keys.

## Configuration

| Env var                | Default                                   | Meaning                       |
|------------------------|-------------------------------------------|-------------------------------|
| `IRCLAUDE_APPS_ROOT`   | `~/projects`                              | Where to scan for projects    |
| `IRCLAUDE_DATA_DIR`    | `$XDG_DATA_HOME/irclaude`                 | DB + ergo binary + run dir    |
| `IRCLAUDE_CONFIG_FILE` | `$XDG_CONFIG_HOME/irclaude/config.toml`   | TOML overrides                |
| `IRCLAUDE_HOST`        | `127.0.0.1`                               | ergo bind address             |
| `IRCLAUDE_PORT`        | `6667`                                    | ergo bind port                |
| `ANTHROPIC_API_KEY`    | (unset)                                   | Pay-as-you-go auth (optional) |

`config.toml` schema:

```toml
apps_root = "/srv/projects"
host = "127.0.0.1"
port = 6667
```

## CLI reference

| Command                 | What it does                                          |
|-------------------------|-------------------------------------------------------|
| `irclaude setup`        | First-run wizard (ergo, projects, WeeChat)            |
| `irclaude up`           | Background bridge + foreground WeeChat (one terminal) |
| `irclaude doctor`       | Re-run prerequisite checks                            |
| `irclaude start`        | Foreground ergo + bridge                              |
| `irclaude stop`         | SIGTERM the running bridge                            |
| `irclaude status`       | Component table                                       |
| `irclaude scan`         | Re-scan apps_root for new projects                    |
| `irclaude list`         | List registered projects                              |
| `irclaude search <q>`   | Full-text search across all project memories         |
| `irclaude decisions <p>`| List recorded decisions for a project                 |
| `irclaude setup-weechat`| Re-link plugin + re-add WeeChat server entry         |
| `irclaude version`      | Print version                                         |

## FAQ

**Why no API key by default?** Because most users run `claude` locally with a
subscription. Forcing API-key auth would double-bill subscribers. The bridge
shells out to the `claude` CLI, which already knows how to authenticate.

**Without the WeeChat plugin?** Chat still works on any IRC client (Hexchat,
irssi, even `ircii`). Code blocks appear as raw `BATCH` lines (visible,
unstyled). Agents still show up as JOIN/PART nicks. The plugin only adds
rendering polish.

**Can I run multiple Claude conversations in parallel?** Yes — each channel
is an independent session with its own UUID and digest. Cross-channel context
sharing is on the roadmap (`/recall <project>` slash command).

**Why ergo and not InspIRCd / UnrealIRCd?** ergo is a single Go binary, ships
IRCv3 features (message-tags, BATCH, draft/multiline) out of the box, and
needs zero config to run on `127.0.0.1`. Drop-in replaceable if you'd rather.

## Contributing

```sh
pip install -e ".[dev]"
pytest -q
```

The 10 integration tests that talk to a real ergo binary are skipped if
ergo isn't on `$PATH`. Run `irclaude setup` once or install ergo via
your package manager (`apt install ergo`, `brew install ergo`) to enable them.

## License

MIT — see `LICENSE`.
