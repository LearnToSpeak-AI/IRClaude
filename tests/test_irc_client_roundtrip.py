import asyncio
import shutil
from pathlib import Path

import pytest

from myorch.bridge.ergo_config import generate_ergo_config
from myorch.bridge.server import ErgoServer
from myorch.irc.client import IrcClient
from myorch.irc.messages import Message


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
async def test_tagged_privmsg_roundtrip(running_ergo):
    a = IrcClient("127.0.0.1", running_ergo, nick="alice")
    b = IrcClient("127.0.0.1", running_ergo, nick="bob")
    await a.connect()
    await b.connect()
    await a.expect("001"); await b.expect("001")
    try:
        await a.join("#room")
        await b.join("#room")
        await asyncio.sleep(0.2)
        outbound = Message(
            command="PRIVMSG",
            params=["#room", "hi from alice"],
            tags={"+myorch.kind": "text"},
        )
        await a.send(outbound)
        for _ in range(50):
            msg = await asyncio.wait_for(b.recv(), timeout=2.0)
            if msg.command == "PRIVMSG" and msg.params[0] == "#room":
                assert msg.params[1] == "hi from alice"
                assert msg.tags.get("+myorch.kind") == "text"
                break
        else:
            pytest.fail("never received PRIVMSG")
    finally:
        await a.close()
        await b.close()
