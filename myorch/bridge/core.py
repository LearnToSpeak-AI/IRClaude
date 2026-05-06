import asyncio
import contextlib
import signal as _signal
from pathlib import Path

from myorch.bridge.agents import AgentManager
from myorch.bridge.claude_runner import ClaudeRunner
from myorch.bridge.codeblock import CodeBlockBuffer
from myorch.bridge.event_translator import classify_agent_events, translate
from myorch.bridge.router import ChannelRouter
from myorch.bridge.session_setup import prepare_session
from myorch.config import Settings
from myorch.irc.client import IrcClient
from myorch.irc.messages import Message
from myorch.services.memory_service import MemoryService

BOT_NICK = "claude"


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
            if not target.startswith("#"):
                continue
            await self.router.dispatch_message(target, text)

    async def _handle_turn(self, channel: str, prompt: str) -> None:
        project = self.router.project_for_channel(channel)
        if project is None:
            return
        ctx = prepare_session(project=project, memory=self.memory, settings=self.settings)
        self.router.bind_session(channel, ctx.session_id)
        turn_id = self._turn_counters.get(channel, 0) + 1
        self._turn_counters[channel] = turn_id

        runner = ClaudeRunner(
            cwd=Path(project.path),
            claude_uuid=ctx.claude_uuid,
            mcp_config_path=ctx.mcp_config_path,
            digest_path=ctx.digest_path,
            executable=self.claude_executable,
        )
        buffer = CodeBlockBuffer(channel=channel, session_id=ctx.claude_uuid, turn_id=turn_id)
        async for event in runner.run_turn(prompt):
            starts, ends, normal = classify_agent_events([event])
            for s in starts:
                await self.agents.agent_start(s["name"], channel)
            for n in normal:
                msgs = translate(
                    n,
                    channel=channel,
                    session_id=ctx.claude_uuid,
                    turn_id=turn_id,
                    agent_nick=n.get("subagent"),
                )
                for m in msgs:
                    text = m.params[1] if len(m.params) > 1 else ""
                    if m.tags.get("+myorch.kind") in {"text", "agent-msg"}:
                        for line in buffer.feed(text + "\n"):
                            await self._send_raw(line)
                    else:
                        await self.client.send(m)
            for e in ends:
                await self.agents.agent_end(e["name"], channel)
        for line in buffer.flush():
            await self._send_raw(line)

    async def _send_raw(self, wire_line: str) -> None:
        assert self.client is not None
        line = wire_line.rstrip("\r\n")
        await self.client._send_raw(line)

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
