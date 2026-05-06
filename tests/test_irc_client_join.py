import asyncio
import shutil
from pathlib import Path

import pytest

from myorch.bridge.ergo_config import generate_ergo_config
from myorch.bridge.server import ErgoServer
from myorch.irc.client import IrcClient


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
async def test_join_emits_join_353_366(running_ergo):
    client = IrcClient("127.0.0.1", running_ergo, nick="joiner")
    await client.connect()
    await client.expect("001")
    try:
        joined = []
        await client.join("#myorch-test")
        deadline = asyncio.get_event_loop().time() + 4.0
        while {("JOIN",), ("353",), ("366",)} - {(c,) for c in joined}:
            if asyncio.get_event_loop().time() > deadline:
                pytest.fail(f"missing replies; have {joined}")
            msg = await asyncio.wait_for(client.recv(), timeout=1.0)
            joined.append(msg.command)
        assert "JOIN" in joined
        assert "353" in joined
        assert "366" in joined
    finally:
        await client.close()
