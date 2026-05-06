import asyncio

import pytest

from myorch.bridge.router import ChannelRouter
from myorch.db import connect, init_schema
from myorch.models import Project
from myorch.services.memory_service import MemoryService


def _memory(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    return MemoryService(conn)


@pytest.mark.asyncio
async def test_shutdown_all_closes_each_active_session(tmp_path):
    mem = _memory(tmp_path)
    sessions = []
    for name in ["A", "B", "C"]:
        proj = mem.upsert_project(Project(name=name, path=str(tmp_path / name)))
        sessions.append(mem.start_session(proj.id))

    router = ChannelRouter(memory=mem)
    router.channels_for_known_projects()
    for chan, sess in zip(["#a", "#b", "#c"], sessions):
        router.bind_session(chan, sess.id)

    async def runner(channel: str, prompt: str) -> None:
        sid = router._sessions[channel]
        mem.save_summary(sid, f"ok {channel}")

    router.set_runner(runner)
    await router.shutdown_all(poll_interval=0.05, max_wait=2.0)

    for sess in sessions:
        refreshed = mem.get_session(sess.id)
        assert refreshed.summary is not None
        assert refreshed.status.value == "closed"
