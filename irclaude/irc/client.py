import asyncio
import contextlib
from typing import AsyncIterator

from irclaude.irc.messages import Message, parse_line

_REQUESTED_CAPS = (
    "message-tags",
    "batch",
    "draft/multiline",
    "labeled-response",
    "server-time",
    "message-ids",
    "account-tag",
)


class IrcClient:
    def __init__(self, host: str, port: int, nick: str, *, user: str | None = None,
                 realname: str | None = None) -> None:
        self.host = host
        self.port = port
        self.nick = nick
        self.user = user or nick
        self.realname = realname or nick
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.acked_caps: set[str] = set()
        self._listener: asyncio.Task | None = None
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._closed = False

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._closed

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._listener = asyncio.create_task(self._read_loop())
        await self._negotiate_caps()
        await self._send_raw(f"NICK {self.nick}")
        await self._send_raw(f"USER {self.user} 0 * :{self.realname}")

    async def _negotiate_caps(self) -> None:
        await self._send_raw("CAP LS 302")
        offered: set[str] = set()
        while True:
            msg = await self._inbox.get()
            if msg.command == "CAP" and msg.params[1] == "LS":
                trailing = msg.params[-1]
                offered.update(trailing.split())
                if msg.params[1] == "LS" and len(msg.params) >= 4 and msg.params[2] == "*":
                    continue
                break
        wanted = [c for c in _REQUESTED_CAPS if c in offered]
        if wanted:
            await self._send_raw("CAP REQ :" + " ".join(wanted))
            ack = await self._inbox.get()
            if ack.command == "CAP" and ack.params[1] == "ACK":
                self.acked_caps = set(ack.params[-1].split())
        await self._send_raw("CAP END")

    async def _send_raw(self, line: str) -> None:
        assert self._writer is not None
        self._writer.write((line + "\r\n").encode("utf-8"))
        await self._writer.drain()

    async def send(self, msg: Message) -> None:
        await self._send_raw(msg.encode().rstrip("\r\n"))

    async def send_text(self, target: str, text: str, tags: dict[str, str] | None = None) -> None:
        await self.send(Message(command="PRIVMSG", params=[target, text], tags=tags or {}))

    async def recv(self) -> Message:
        return await self._inbox.get()

    async def expect(self, command: str) -> Message:
        while True:
            msg = await self._inbox.get()
            if msg.command == command:
                return msg

    async def join(self, channel: str) -> None:
        await self._send_raw(f"JOIN {channel}")

    async def stream(self) -> AsyncIterator[Message]:
        while not self._closed:
            yield await self._inbox.get()

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while True:
            try:
                raw = await self._reader.readline()
            except (ConnectionResetError, asyncio.IncompleteReadError):
                return
            if not raw:
                return
            try:
                msg = parse_line(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if msg.command == "PING":
                token = msg.params[0] if msg.params else ""
                await self._send_raw(f"PONG :{token}")
                continue
            await self._inbox.put(msg)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._writer is not None:
            with contextlib.suppress(Exception):
                await self._send_raw("QUIT :bye")
            with contextlib.suppress(Exception):
                self._writer.close()
                await self._writer.wait_closed()
        if self._listener is not None:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener
        self._writer = None
        self._reader = None
        self._listener = None
