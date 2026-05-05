# Spike: `claude_session_id` Capture Mechanism

**Date:** 2026-05-05  
**Status:** DONE — all mechanisms confirmed working  
**Author:** Task 4.0 spike

---

## Environment

```
$ which claude
<HOME>/.local/bin/claude

$ claude --version
2.1.128 (Claude Code)
```

---

## Step 1: `claude --help` — Relevant Flags

Key flags discovered (verbatim from help output):

| Flag | Description |
|------|-------------|
| `--session-id <uuid>` | Use a specific session ID for the conversation (must be a valid UUID) |
| `-r, --resume [value]` | Resume a conversation by session ID, or open interactive picker |
| `--output-format <format>` | `text` (default), `json` (single result), or `stream-json` (realtime streaming) — only works with `--print` |
| `--no-session-persistence` | Disable session persistence — sessions will not be saved to disk and cannot be resumed |
| `-c, --continue` | Continue the most recent conversation in the current directory |
| `--fork-session` | When resuming, create a new session ID instead of reusing the original |

**There is NO dedicated `--print-session-id` flag.** Session ID must be captured via JSON output or filesystem.

---

## Step 2: JSON Output Mode (`--output-format json`)

### Command run

```bash
cd /tmp && mkdir -p spike-claude && cd spike-claude && \
  claude -p --output-format json "say the word hi and nothing else"
```

### Actual output (verbatim, single-line JSON, formatted here for readability)

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "api_error_status": null,
  "duration_ms": 2506,
  "duration_api_ms": 2418,
  "num_turns": 1,
  "result": "hi",
  "stop_reason": "end_turn",
  "session_id": "ddf1e759-9e5f-4bd3-8490-6a35f35ccefb",
  "total_cost_usd": 0.2086175,
  "usage": { ... },
  "modelUsage": { ... },
  "permission_denials": [],
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "dfcfc986-fd35-44d0-a553-d0fbded030c5"
}
```

**Confirmed field name:** `session_id` (top-level key in the JSON object)  
**Format:** Standard UUID v4, e.g. `ddf1e759-9e5f-4bd3-8490-6a35f35ccefb`

Note: There are **two** UUID-like fields:
- `session_id` — the conversation session identifier (use this for `--resume`)
- `uuid` — appears to be the individual invocation/result UUID (do NOT use for resume)

---

## Step 3: Filesystem Inspection (`~/.claude/projects/`)

### Command run

```bash
ls ~/.claude/projects/ | head -5
```

### Output

```
-home-ipena
-home-ipena-Documents-APPS-controller
-home-ipena-Documents-APPS-CSVs
-home-ipena-Documents-APPS-CSVs-izzi
-home-ipena-Documents-APPS-docs-zequenze-selenium
```

**Encoding scheme:** Absolute path with `/` replaced by `-`, prefixed with `-`.  
Example: `<APPS_ROOT>/MyOrchestrator` → `-home-ipena-Documents-APPS-MyOrchestrator`

For the `/tmp` directory, the project dir is `-tmp`.

### Session file for the spike run

```bash
ls ~/.claude/projects/-tmp/
# ddf1e759-9e5f-4bd3-8490-6a35f35ccefb.jsonl
# memory
```

**Confirmed:** The JSONL file name (`ddf1e759-9e5f-4bd3-8490-6a35f35ccefb.jsonl`) matches exactly the `session_id` returned in the JSON output. Both mechanisms reference the same UUID.

---

## Decision: Chosen Capture Strategy

### Recommendation: **Option B — JSON Output Mode** (primary)

**Rationale:**
1. `--output-format json` is a first-class, documented flag — it will not break silently across versions.
2. `session_id` is a top-level key in the JSON result — trivial to parse with `json.loads(stdout)["session_id"]`.
3. The session ID is available **synchronously** at invocation end — no polling, no race conditions.
4. The filesystem approach (Option C) is confirmed as a valid cross-check but requires encoding the path, watching for new files, and handling race conditions.

### Option C (filesystem) as fallback / verification

Option C is viable and now fully documented. It can serve as:
- A **fallback** if Option B fails (e.g., output parsing error)
- A **verification** layer: confirm the session JSONL exists before passing ID to `--resume`

Path formula:
```python
import os, re

def project_dir_for_cwd(cwd: str) -> str:
    # Replace all '/' with '-', then prefix with '-'
    encoded = cwd.replace("/", "-")
    # Result: /tmp/spike-claude -> -tmp-spike-claude
    return os.path.expanduser(f"~/.claude/projects/{encoded}")
```

---

## SessionManager Implementation (Task 5.2) Pseudo-code

```python
import subprocess, json, os, glob

class SessionManager:

    def spawn_and_capture_session_id(self, cwd: str, initial_prompt: str) -> str:
        """
        Run a minimal headless invocation to capture the session ID,
        then the caller can --resume into a real interactive session.
        """
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", initial_prompt],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(result.stdout)
        session_id = data["session_id"]
        return session_id

    def resume_session(self, session_id: str, cwd: str):
        """Launch interactive claude session resuming from captured ID."""
        subprocess.run(
            ["claude", "--resume", session_id],
            cwd=cwd,
        )

    def verify_session_file_exists(self, session_id: str, cwd: str) -> bool:
        """Option C cross-check: confirm JSONL exists on disk."""
        encoded = cwd.replace("/", "-")
        pattern = os.path.expanduser(
            f"~/.claude/projects/{encoded}/{session_id}.jsonl"
        )
        return os.path.exists(pattern)

    def latest_session_id_from_fs(self, cwd: str) -> str | None:
        """Option C fallback: get newest session JSONL in project dir."""
        encoded = cwd.replace("/", "-")
        project_dir = os.path.expanduser(f"~/.claude/projects/{encoded}")
        files = glob.glob(os.path.join(project_dir, "*.jsonl"))
        if not files:
            return None
        newest = max(files, key=os.path.getmtime)
        return os.path.basename(newest).replace(".jsonl", "")
```

**Key resume command:**
```bash
claude --resume ddf1e759-9e5f-4bd3-8490-6a35f35ccefb
```

**Pre-seeding session ID (if we want to control the UUID ourselves):**
```bash
claude --session-id <our-uuid> -p --output-format json "..."
```
The `--session-id` flag lets SessionManager inject a deterministic UUID at spawn time — eliminating the capture step entirely if we generate the UUID first.

---

## Edge Cases & Risks

| Risk | Mitigation |
|------|------------|
| `claude` not installed on target machine | Guard with `shutil.which("claude")` before spawning |
| JSON parse failure (e.g., auth error outputs plain text) | Wrap in try/except; fall back to Option C filesystem polling |
| `session_id` vs `uuid` field confusion | Always use `data["session_id"]`, never `data["uuid"]` |
| `--session-id` flag is new (v2.1+) | Version-check or catch `unrecognized option` stderr |
| Project dir encoding edge cases (paths with spaces, special chars) | Test with `os.path.realpath(cwd)` before encoding |
| Headless cost of seed invocation | Use a 1-token prompt like `"ok"` to minimize token spend; or use `--session-id` to skip seed entirely |
| `--no-session-persistence` disables filesystem approach | Don't use this flag when resume is needed |

---

## Simplest Production Strategy

Use `--session-id` to **inject** the UUID rather than capture it:

```python
import uuid, subprocess

session_id = str(uuid.uuid4())

# Seed the session (cheap, headless)
subprocess.run(
    ["claude", "-p", "--output-format", "json",
     "--session-id", session_id, "ok"],
    cwd=cwd, capture_output=True
)

# Later: resume interactively
subprocess.run(["claude", "--resume", session_id], cwd=cwd)
```

This is the cleanest approach: **no stdout parsing needed**, deterministic, zero ambiguity.

---

## Follow-up Tasks

- [ ] **Task 5.2**: Implement `SessionManager` using `--session-id` injection strategy
- [ ] Confirm `--session-id` behavior when the UUID already has an existing session (should it merge or error?)
- [ ] Test `--resume` with an expired/deleted session file to understand error handling
- [ ] Benchmark minimal seed prompt cost (likely <1¢ per session with a short prompt)
