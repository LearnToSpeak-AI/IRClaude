# MyOrchestrator

Local web orchestrator for managing multiple Claude Code sessions across projects in `~/Documents/APPS/`. Single browser pane: project list, terminal per project, dev server controls, persistent memory in SQLite.

**No API key.** Uses your authenticated `claude` CLI subprocess (Pro/Max subscription).

## Requirements

- Python 3.11+
- `claude` CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code`)
- Linux/macOS

## Install

```bash
git clone <repo> && cd MyOrchestrator
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
. .venv/bin/activate
uvicorn myorch.app:create_app --factory --host 127.0.0.1 --port 7000
```

Open http://127.0.0.1:7000 — click "+ Scan" to discover your projects.

## Configuration

Environment variables (defaults shown):
- `MYORCH_APPS_ROOT=/home/$USER/Documents/APPS`
- `MYORCH_DATA_DIR=$HOME/.myorch`
- `MYORCH_TMP_DIR=/tmp/myorch`
- `MYORCH_HOST=127.0.0.1`
- `MYORCH_PORT=7000`

## Tests

```bash
pytest -v
```

## Architecture

See `docs/superpowers/specs/2026-05-05-myorchestrator-design.md`.
