import asyncio
import re
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable

from myorch.models import Project, SessionStatus
from myorch.services.memory_service import MemoryService

RunnerFn = Callable[[str, str], Awaitable[None]]


@dataclass
class SessionContext:
    project: Project
    session_id: int
    claude_uuid: str


_NON_CHAN = re.compile(r"[^a-z0-9-]")
_DASH_RUN = re.compile(r"-+")

_SUMMARY_PROMPT_ES = (
    "Por favor guarda un resumen breve de lo que hicimos en esta sesión "
    "usando la herramienta save_summary del MCP myorch (en español)."
)


def project_to_channel(name: str) -> str:
    lowered = name.lower()
    cleaned = _NON_CHAN.sub("-", lowered)
    cleaned = _DASH_RUN.sub("-", cleaned).strip("-")
    if not cleaned:
        cleaned = "project"
    cleaned = cleaned[:49]
    return "#" + cleaned


def _disambiguate(channels: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for chan in channels:
        if chan not in seen:
            seen[chan] = 1
            out.append(chan)
            continue
        seen[chan] += 1
        out.append(f"{chan}-{seen[chan]}")
    return out


class _ChannelQueue:
    def __init__(self, runner: RunnerFn, channel: str) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._runner = runner
        self._channel = channel

    def ensure_started(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def put(self, text: str) -> None:
        self.ensure_started()
        await self._queue.put(text)

    async def drain(self) -> None:
        await self._queue.join()

    async def _loop(self) -> None:
        while True:
            text = await self._queue.get()
            try:
                await self._runner(self._channel, text)
            finally:
                self._queue.task_done()


class ChannelRouter:
    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory
        self._cache: dict[str, Project] = {}
        self._queues: dict[str, _ChannelQueue] = {}
        self._runner: RunnerFn | None = None

    def channels_for_known_projects(self) -> list[str]:
        projects = self.memory.list_projects()
        chans = [project_to_channel(p.name) for p in projects]
        out = _disambiguate(chans)
        self._cache = {c: p for c, p in zip(out, projects)}
        return out

    def project_for_channel(self, channel: str) -> Project | None:
        if not self._cache:
            self.channels_for_known_projects()
        return self._cache.get(channel)

    def set_runner(self, runner: RunnerFn) -> None:
        self._runner = runner

    def start_session(self, channel: str) -> SessionContext:
        project = self.project_for_channel(channel)
        if project is None or project.id is None:
            raise KeyError(channel)
        session = self.memory.start_session(project.id)
        claude_uuid = project.last_session_id or str(uuid.uuid4())
        if not project.last_session_id:
            self.memory.set_claude_session_id(session.id, claude_uuid)
        return SessionContext(
            project=project,
            session_id=session.id,
            claude_uuid=claude_uuid,
        )

    async def dispatch_message(self, channel: str, text: str) -> None:
        if self.project_for_channel(channel) is None:
            return
        if self._runner is None:
            raise RuntimeError("router has no runner")
        queue = self._queues.setdefault(channel, _ChannelQueue(self._runner, channel))
        await queue.put(text)

    async def drain(self, channel: str) -> None:
        q = self._queues.get(channel)
        if q is not None:
            await q.drain()

    def bind_session(self, channel: str, session_id: int) -> None:
        self._sessions = getattr(self, "_sessions", {})
        self._sessions[channel] = session_id

    async def idle_close(
        self,
        channel: str,
        *,
        poll_interval: float = 1.0,
        max_wait: float = 30.0,
    ) -> None:
        sessions = getattr(self, "_sessions", {})
        session_id = sessions.get(channel)
        if session_id is None or self._runner is None:
            return
        await self._runner(channel, _SUMMARY_PROMPT_ES)
        deadline = asyncio.get_event_loop().time() + max_wait
        while asyncio.get_event_loop().time() < deadline:
            sess = self.memory.get_session(session_id)
            if sess and sess.summary:
                break
            await asyncio.sleep(poll_interval)
        self.memory.close_session(session_id, SessionStatus.closed)
