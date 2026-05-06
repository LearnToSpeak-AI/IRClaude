import asyncio
import shutil
from pathlib import Path

import pytest

from irclaude.bridge.ergo_config import generate_ergo_config
from irclaude.bridge.server import ErgoServer
from irclaude.irc.client import IrcClient


pytestmark = pytest.mark.skipif(
    shutil.which("ergo") is None, reason="ergo binary required"
)


@pytest.fixture
async def running_ergo(tmp_path: Path, free_port: int):
    cfg_path = tmp_path / "ergo.yaml"
    cfg_path.write_text(generate_ergo_config("127.0.0.1", free_port), encoding="utf-8")
    server = ErgoServer(binary_path=Path(shutil.which("ergo")), config_path=cfg_path)
    await server.start()
    for _ in range(40):
        try:
            r, w = await asyncio.open_connection("127.0.0.1", free_port)
            w.close()
            await w.wait_closed()
            break
        except OSError:
            await asyncio.sleep(0.05)
    try:
        yield free_port
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_connect_negotiates_caps_and_receives_001(running_ergo):
    port = running_ergo
    client = IrcClient(host="127.0.0.1", port=port, nick="tester")
    await client.connect()
    try:
        welcome = await asyncio.wait_for(client.expect("001"), timeout=5.0)
        assert welcome.command == "001"
        assert welcome.params[0] == "tester"
        assert "message-tags" in client.acked_caps
        assert "batch" in client.acked_caps
        assert "draft/multiline" in client.acked_caps
        assert "labeled-response" in client.acked_caps
        assert "server-time" in client.acked_caps
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_close_is_idempotent(running_ergo):
    client = IrcClient("127.0.0.1", running_ergo, nick="t2")
    await client.connect()
    await client.close()
    await client.close()  # must not raise
