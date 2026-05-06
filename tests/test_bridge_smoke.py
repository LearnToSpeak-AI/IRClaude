import asyncio
import shutil
import stat
from pathlib import Path

import pytest

from irclaude.bridge import Bridge
from irclaude.bridge.ergo_config import generate_ergo_config
from irclaude.bridge.server import ErgoServer
from irclaude.config import Settings
from irclaude.db import connect, init_schema
from irclaude.irc.client import IrcClient
from irclaude.models import Project
from irclaude.services.memory_service import MemoryService


pytestmark = pytest.mark.skipif(
    shutil.which("ergo") is None, reason="ergo binary required"
)


def _make_fake_claude(path: Path) -> Path:
    body = (
        "#!/usr/bin/env bash\n"
        "echo '{\"type\":\"assistant\",\"message\":{\"content\":[{\"type\":\"text\",\"text\":\"hello back\"}]}}'\n"
        "echo '{\"type\":\"result\",\"subtype\":\"success\"}'\n"
    )
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.mark.asyncio
async def test_bridge_replies_to_user_privmsg(tmp_path, free_port):
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

    fake = _make_fake_claude(tmp_path / "claude")

    settings = Settings(
        apps_root=tmp_path / "apps",
        data_dir=tmp_path / "data",
        config_file=tmp_path / "cfg.toml",
        host="127.0.0.1",
        port=free_port,
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path); init_schema(conn)
    mem = MemoryService(conn)
    proj_path = tmp_path / "apps" / "demo"
    proj_path.mkdir(parents=True)
    mem.upsert_project(Project(name="Demo", path=str(proj_path)))

    bridge = Bridge(settings=settings, memory=mem, claude_executable=fake)
    bridge_task = asyncio.create_task(bridge.run())
    try:
        await asyncio.sleep(1.0)

        user = IrcClient("127.0.0.1", free_port, nick="user")
        await user.connect()
        await user.expect("001")
        await user.join("#demo")
        await asyncio.sleep(0.3)
        await user.send_text("#demo", "hi")

        deadline = asyncio.get_event_loop().time() + 8.0
        seen_reply = False
        while asyncio.get_event_loop().time() < deadline:
            msg = await asyncio.wait_for(user.recv(), timeout=2.0)
            if (
                msg.command == "PRIVMSG"
                and msg.params[0] == "#demo"
                and "hello back" in msg.params[1]
            ):
                seen_reply = True
                break
        assert seen_reply
        await user.close()
    finally:
        await bridge.stop()
        bridge_task.cancel()
        try:
            await bridge_task
        except asyncio.CancelledError:
            pass
        await server.stop()
