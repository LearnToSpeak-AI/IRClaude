import asyncio
import contextlib
import re
import signal as _signal
from pathlib import Path

from irclaude.bridge.agents import AgentManager
from irclaude.bridge.claude_runner import ClaudeRunner
from irclaude.bridge.codeblock import CodeBlockBuffer
from irclaude.bridge.event_translator import classify_agent_events, translate
from irclaude.bridge.router import ChannelRouter
from irclaude.bridge.session_setup import prepare_session
from irclaude.config import Settings
from irclaude.irc.client import IrcClient
from irclaude.irc.messages import Message
from irclaude.services.memory_service import MemoryService

BOT_NICK = "claude"


_PROMPT_PREFIX = """\
[IRClaude bridge — read carefully before answering]
You are responding in an IRC channel that is rendered live in WeeChat.
- Use markdown FREELY: bold (**x**), italic (*x*), inline code (`x`),
  fenced code blocks (```lang …```), tables (| col | col | + |---|---|),
  bulleted lists (- item), checklists (- [ ] / - [x]), blockquotes (> x),
  strikethrough (~~x~~), links ([text](url)), headings (# / ##).
- The bridge converts all of these to IRC formatting: tables become ASCII grids,
  code blocks render inline with Pygments syntax highlighting.
- DO NOT use Write or Edit to save the answer to a file. The user is reading IRC,
  there is no file viewer.
- DO NOT keep the response under any word limit. Scrollback handles long answers.
- Any earlier hook/MCP policy that says "save artifacts to files", "respond under
  N words", or "use Write tool for code/configs/PRDs" was authored for a different
  surface and DOES NOT APPLY to this IRC channel — disregard it for this turn.
- Speak the answer directly in your reply.

User question:
"""


def _wrap_prompt(prompt: str) -> str:
    return _PROMPT_PREFIX + prompt


_NICK_SAFE = re.compile(r"[^a-z0-9-]")


def _detect_task_lifecycle(
    event: dict,
    active_tasks: dict[str, str],
    counter: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Walk a stream-json event looking for Task tool_use / tool_result events.

    Returns (newly_started_nicks, newly_ended_nicks). Mutates ``active_tasks``
    (task_id -> nick) and ``counter`` (slug -> next index) so callers track
    state across the turn.
    """
    starts: list[str] = []
    ends: list[str] = []
    et = event.get("type")
    if et == "assistant":
        msg = event.get("message") or {}
        for item in msg.get("content") or []:
            # Claude CLI 2.1.x renames the Task tool to "Agent" in its
            # stream-json output. Accept both for forward/backward compat.
            if item.get("type") == "tool_use" and item.get("name") in {"Agent", "Task"}:
                task_id = item.get("id") or ""
                if not task_id or task_id in active_tasks:
                    continue
                input_ = item.get("input") or {}
                raw = (input_.get("subagent_type") or "agent").lower()
                slug = _NICK_SAFE.sub("", raw)[:12] or "agent"
                counter[slug] = counter.get(slug, 0) + 1
                nick = f"{slug}-{counter[slug]}"
                active_tasks[task_id] = nick
                starts.append(nick)
    elif et == "user":
        msg = event.get("message") or {}
        for item in msg.get("content") or []:
            if item.get("type") == "tool_result":
                tool_use_id = item.get("tool_use_id") or ""
                nick = active_tasks.pop(tool_use_id, None)
                if nick is not None:
                    ends.append(nick)
    return starts, ends


class Bridge:
    def __init__(
        self,
        settings: Settings,
        memory: MemoryService,
        *,
        claude_executable: Path | str = "claude",
        bot_nick: str = BOT_NICK,
    ) -> None:
        self.settings = settings
        self.memory = memory
        self.claude_executable = claude_executable
        self.bot_nick = bot_nick
        self.router = ChannelRouter(memory=memory)
        self.client: IrcClient | None = None
        self.agents: AgentManager | None = None
        self._running = False
        self._turn_counters: dict[str, int] = {}

    def _agent_factory(self, nick: str) -> IrcClient:
        return IrcClient(host=self.settings.host, port=self.settings.port, nick=nick)

    async def run(self) -> None:
        self._running = True
        self.client = IrcClient(
            host=self.settings.host, port=self.settings.port, nick=self.bot_nick
        )
        self.agents = AgentManager(irc_factory=self._agent_factory)
        await self.client.connect()
        await self.client.expect("001")
        for chan in self.router.channels_for_known_projects():
            await self.client.join(chan)
            await self._set_topic_for_channel(chan)
        self.router.set_runner(self._handle_turn)

        async for msg in self.client.stream():
            if not self._running:
                break
            if msg.command != "PRIVMSG":
                continue
            target = msg.params[0]
            text = msg.params[1] if len(msg.params) > 1 else ""
            if msg.prefix and msg.prefix.startswith(self.bot_nick):
                continue
            # Any PRIVMSG that carries an `+irclaude.*` tag was emitted by
            # this bridge (main claude or one of its sub-agents) and must NOT
            # trigger another turn. Without this filter, the sub-agent's
            # `<explore-1>` chatter loops back as fake user input.
            if any(k.startswith("+irclaude.") for k in msg.tags):
                continue
            if not target.startswith("#"):
                continue
            await self.router.dispatch_message(target, text)

    async def _handle_turn(self, channel: str, prompt: str) -> None:
        project = self.router.project_for_channel(channel)
        if project is None:
            print(f"[bridge] no project bound to {channel}, ignoring: {prompt!r}")
            return
        ctx = prepare_session(project=project, memory=self.memory, settings=self.settings)
        self.router.bind_session(channel, ctx.session_id)
        turn_id = self._turn_counters.get(channel, 0) + 1
        self._turn_counters[channel] = turn_id
        mode = "resume" if ctx.is_resume else "new"
        print(
            f"[bridge] turn {turn_id} on {channel} ({project.name}, {mode} {ctx.claude_uuid}): "
            f"{prompt!r}"
        )
        # Refresh the channel topic with the current question so the title
        # bar acts like a "now-working-on" indicator.
        topic_hint = prompt.strip().splitlines()[0] if prompt.strip() else None
        if topic_hint and len(topic_hint) > 80:
            topic_hint = topic_hint[:77] + "..."
        await self._set_topic_for_channel(channel, hint=topic_hint)

        runner = ClaudeRunner(
            cwd=Path(project.path),
            claude_uuid=ctx.claude_uuid,
            mcp_config_path=ctx.mcp_config_path,
            digest_path=ctx.digest_path,
            executable=self.claude_executable,
            is_resume=ctx.is_resume,
        )
        buffer = CodeBlockBuffer(channel=channel, session_id=ctx.claude_uuid, turn_id=turn_id)
        # Per-turn Task lifecycle tracking: claude 2.1.x emits a `tool_use`
        # named "Agent" (formerly "Task") for each subagent dispatch and a
        # matching `tool_result` when it ends. Translate those into
        # agent_start/agent_end so a real IRC client JOIN/PARTs the channel.
        active_tasks: dict[str, str] = {}
        agent_counter: dict[str, int] = {}
        try:
            async for event in runner.run_turn(_wrap_prompt(prompt)):
                task_starts, task_ends = _detect_task_lifecycle(
                    event, active_tasks, agent_counter
                )
                for nick in task_starts:
                    await self.agents.agent_start(nick, channel)
                starts, ends, normal = classify_agent_events([event])
                for s in starts:
                    await self.agents.agent_start(s["name"], channel)
                # Route any event whose parent_tool_use_id matches an active
                # subagent through that subagent's IRC client so its tool
                # calls and intermediate text appear as `<explore-1>`, not
                # `<@claude>`.
                parent_id = event.get("parent_tool_use_id")
                sub_nick = active_tasks.get(parent_id) if parent_id else None
                for n in normal:
                    msgs = translate(
                        n,
                        channel=channel,
                        session_id=ctx.claude_uuid,
                        turn_id=turn_id,
                        agent_nick=sub_nick,
                    )
                    for m in msgs:
                        text = m.params[1] if len(m.params) > 1 else ""
                        kind = m.tags.get("+irclaude.kind")
                        if sub_nick:
                            # Subagent stream: skip the codeblock buffer and
                            # emit each rendered line directly from its own
                            # IRC client.
                            from irclaude.bridge.markdown import markdown_to_irc
                            if kind in {"text", "agent-msg"}:
                                rendered = markdown_to_irc(text)
                                for line in rendered.split("\n"):
                                    await self.agents.agent_say(
                                        sub_nick,
                                        channel,
                                        Message(
                                            command="PRIVMSG",
                                            params=[channel, line or " "],
                                            tags=dict(m.tags),
                                        ),
                                    )
                            else:
                                await self.agents.agent_say(sub_nick, channel, m)
                        elif kind in {"text", "agent-msg"}:
                            for line in buffer.feed(text + "\n"):
                                await self._send_raw(line)
                        else:
                            await self.client.send(m)
                for e in ends:
                    await self.agents.agent_end(e["name"], channel)
                for nick in task_ends:
                    await self.agents.agent_end(nick, channel)
            for line in buffer.flush():
                await self._send_raw(line)
            # Defensive: any task that never received a tool_result (claude
            # crashed mid-task, etc.) should still PART so the nick doesn't
            # linger in the channel.
            for nick in list(active_tasks.values()):
                with contextlib.suppress(Exception):
                    await self.agents.agent_end(nick, channel)
        except Exception as exc:
            print(f"[bridge] turn {turn_id} on {channel} failed: {exc!r}")
        result = runner.last_result
        if result is not None and result.exit_code != 0:
            print(
                f"[bridge] claude exited {result.exit_code} on {channel}; "
                f"stderr: {result.stderr.strip()!r}"
            )

    async def _send_raw(self, wire_line: str) -> None:
        assert self.client is not None
        line = wire_line.rstrip("\r\n")
        await self.client._send_raw(line)

    async def _set_topic_for_channel(self, channel: str, hint: str | None = None) -> None:
        """Populate the channel topic so WeeChat's title bar isn't a blank
        band. Default topic is `<project>: <last decision or hint>`. Falls back
        to the channel name if nothing else is known.
        """
        if self.client is None:
            return
        # Always prefix with the channel name (e.g. `#controller`) so the
        # title bar reads `#controller: <topic>` even before any decision is
        # known.
        text = channel
        project = self.router.project_for_channel(channel)
        tail = hint
        if not tail and project is not None:
            decisions = self.memory.list_decisions(project.id)
            if decisions:
                tail = decisions[0].title
        if tail:
            text = f"{channel}: {tail}"
        text = text.replace("\n", " ").replace("\r", " ")
        if len(text) > 200:
            text = text[:197] + "..."
        with contextlib.suppress(Exception):
            await self.client._send_raw(f"TOPIC {channel} :{text}")

    def _ensure_control_handlers(self) -> None:
        if hasattr(self, "_control_handlers"):
            return
        self._control_handlers = {
            "projects": self._ctl_projects,
            "recall": self._ctl_recall,
            "search": self._ctl_search,
            "decisions": self._ctl_decisions,
            "close": self._ctl_close,
            "agents": self._ctl_agents,
        }

    def _handle_control(self, channel: str, text: str) -> bool:
        self._ensure_control_handlers()
        if not text.startswith("!"):
            return False
        first, _, rest = text[1:].partition(" ")
        handler = self._control_handlers.get(first)
        if handler is None:
            return False
        handler(channel, rest)
        return True

    def _ctl_projects(self, channel: str, args: str) -> None:
        ...

    def _ctl_recall(self, channel: str, args: str) -> None:
        ...

    def _ctl_search(self, channel: str, args: str) -> None:
        ...

    def _ctl_decisions(self, channel: str, args: str) -> None:
        ...

    def _ctl_close(self, channel: str, args: str) -> None:
        ...

    def _ctl_agents(self, channel: str, args: str) -> None:
        ...

    async def stop(self) -> None:
        self._running = False
        if self.agents is not None:
            with contextlib.suppress(Exception):
                await self.agents.close_all()
        if self.client is not None:
            with contextlib.suppress(Exception):
                await self.client.close()

    async def run_with_signals(self) -> None:
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def _request_stop() -> None:
            stop_event.set()

        for sig in (_signal.SIGINT, _signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, _request_stop)

        run_task = asyncio.create_task(self.run())
        stop_wait = asyncio.create_task(stop_event.wait())
        done, _ = await asyncio.wait(
            {run_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED
        )
        if stop_wait in done:
            await self.stop()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run_task
