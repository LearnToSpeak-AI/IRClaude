import asyncio
import shutil
from pathlib import Path

import pytest

from irclaude.bridge.agents import AgentManager
from irclaude.bridge.ergo_config import generate_ergo_config
from irclaude.bridge.server import ErgoServer
from irclaude.irc.client import IrcClient
from irclaude.irc.messages import Message


pytestmark = pytest.mark.skipif(
    shutil.which("ergo") is None, reason="ergo binary required"
)


@pytest.fixture
async def running_ergo(tmp_path: Path, free_port: int):
    cfg = tmp_path / "ergo.yaml"
    cfg.write_text(generate_ergo_config("127.0.0.1", free_port), encoding="utf-8")
    server = ErgoServer(binary_path=Path(shutil.which("ergo")), config_path=cfg)
    await server.start()
    for _ in range(40):
        try:
            r, w = await asyncio.open_connection("127.0.0.1", free_port)
            w.close(); await w.wait_closed()
            break
        except OSError:
            await asyncio.sleep(0.05)
    try:
        yield free_port
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_agent_joins_and_leaves_channel(running_ergo):
    port = running_ergo

    def factory(nick: str) -> IrcClient:
        return IrcClient(host="127.0.0.1", port=port, nick=nick)

    observer = IrcClient("127.0.0.1", port, nick="watcher")
    await observer.connect()
    await observer.expect("001")
    await observer.join("#bots")
    await asyncio.sleep(0.2)

    manager = AgentManager(irc_factory=factory)
    await manager.agent_start("explore-1", "#bots")
    seen_join = False
    for _ in range(40):
        msg = await asyncio.wait_for(observer.recv(), timeout=2.0)
        if msg.command == "JOIN" and msg.prefix and msg.prefix.startswith("explore-1"):
            seen_join = True
            break
    assert seen_join

    await manager.agent_say("explore-1", "#bots", Message(
        command="PRIVMSG",
        params=["#bots", "found 3 files"],
        tags={"+irclaude.kind": "agent-msg", "+irclaude.agent": "explore-1"},
    ))
    seen_msg = False
    for _ in range(40):
        msg = await asyncio.wait_for(observer.recv(), timeout=2.0)
        if (
            msg.command == "PRIVMSG"
            and msg.prefix and msg.prefix.startswith("explore-1")
            and msg.params == ["#bots", "found 3 files"]
        ):
            seen_msg = True
            break
    assert seen_msg

    await manager.agent_end("explore-1", "#bots")
    seen_part = False
    for _ in range(40):
        msg = await asyncio.wait_for(observer.recv(), timeout=2.0)
        if msg.command == "PART" and msg.prefix and msg.prefix.startswith("explore-1"):
            seen_part = True
            break
    assert seen_part

    await observer.close()
    await manager.close_all()
