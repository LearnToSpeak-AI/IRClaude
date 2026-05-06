import asyncio
from typing import Callable

from myorch.irc.client import IrcClient
from myorch.irc.messages import Message


class AgentManager:
    """Maintain one secondary IRC connection per active sub-agent."""

    def __init__(self, irc_factory: Callable[[str], IrcClient]) -> None:
        self._factory = irc_factory
        self._clients: dict[str, IrcClient] = {}

    async def agent_start(self, nick: str, channel: str) -> None:
        if nick in self._clients:
            return
        client = self._factory(nick)
        await client.connect()
        await client.expect("001")
        await client.join(channel)
        self._clients[nick] = client
        await asyncio.sleep(0)

    async def agent_say(self, nick: str, channel: str, message: Message) -> None:
        client = self._clients.get(nick)
        if client is None:
            return
        await client.send(message)

    async def agent_end(self, nick: str, channel: str) -> None:
        client = self._clients.pop(nick, None)
        if client is None:
            return
        await client.send(Message(command="PART", params=[channel, "done"]))
        await asyncio.sleep(0.05)
        await client.close()

    async def close_all(self) -> None:
        for nick, client in list(self._clients.items()):
            await client.close()
        self._clients.clear()
