import asyncio
import shutil
from pathlib import Path

import pytest

from myorch.bridge import Bridge
from myorch.bridge.ergo_config import generate_ergo_config
from myorch.bridge.server import ErgoServer
from myorch.config import Settings
from myorch.db import connect, init_schema
from myorch.services.memory_service import MemoryService


pytestmark = pytest.mark.skipif(
    shutil.which("ergo") is None, reason="ergo binary required"
)


@pytest.mark.asyncio
async def test_bridge_install_signal_handlers_then_shutdown(tmp_path, free_port):
    cfg = tmp_path / "ergo.yaml"
    cfg.write_text(generate_ergo_config("127.0.0.1", free_port), encoding="utf-8")
    server = ErgoServer(binary_path=Path(shutil.which("ergo")), config_path=cfg)
    await server.start()
    for _ in range(40):
        try:
            r, w = await asyncio.open_connection("127.0.0.1", free_port)
            w.close(); await w.wait_closed(); break
        except OSError:
            await asyncio.sleep(0.05)

    settings = Settings(
        apps_root=tmp_path / "apps", data_dir=tmp_path / "data",
        config_file=tmp_path / "cfg.toml", host="127.0.0.1", port=free_port,
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)

    bridge = Bridge(settings=settings, memory=mem)
    task = asyncio.create_task(bridge.run_with_signals())
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert bridge.client is None or not bridge.client.is_connected
    await server.stop()
