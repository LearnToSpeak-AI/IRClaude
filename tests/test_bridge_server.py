import asyncio
import shutil
import socket
from pathlib import Path

import pytest

from myorch.bridge.ergo_config import generate_ergo_config
from myorch.bridge.server import ErgoServer


def _ergo_binary() -> Path | None:
    found = shutil.which("ergo")
    return Path(found) if found else None


pytestmark = pytest.mark.skipif(
    _ergo_binary() is None, reason="ergo binary not installed for integration tests"
)


def _can_connect(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _wait_for_port(host: str, port: int, deadline_s: float) -> bool:
    loop = asyncio.get_event_loop()
    end = loop.time() + deadline_s
    while loop.time() < end:
        if _can_connect(host, port):
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_ergo_server_starts_and_accepts_tcp(tmp_path, free_port):
    cfg_path = tmp_path / "ergo.yaml"
    cfg_path.write_text(generate_ergo_config("127.0.0.1", free_port), encoding="utf-8")
    server = ErgoServer(binary_path=_ergo_binary(), config_path=cfg_path)

    await server.start()
    try:
        assert server.is_running is True
        assert await _wait_for_port("127.0.0.1", free_port, 2.0)
    finally:
        await server.stop()
    assert server.is_running is False


@pytest.mark.asyncio
async def test_ergo_server_stop_is_graceful_then_kill(tmp_path, free_port):
    cfg_path = tmp_path / "ergo.yaml"
    cfg_path.write_text(generate_ergo_config("127.0.0.1", free_port), encoding="utf-8")
    server = ErgoServer(binary_path=_ergo_binary(), config_path=cfg_path, kill_after=0.2)
    await server.start()
    pid = server.pid
    assert pid is not None
    await server.stop()
    assert server.is_running is False


@pytest.mark.asyncio
async def test_ergo_server_double_start_raises(tmp_path, free_port):
    cfg_path = tmp_path / "ergo.yaml"
    cfg_path.write_text(generate_ergo_config("127.0.0.1", free_port), encoding="utf-8")
    server = ErgoServer(binary_path=_ergo_binary(), config_path=cfg_path)
    await server.start()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            await server.start()
    finally:
        await server.stop()
