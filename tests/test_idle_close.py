import asyncio

import pytest

from irclaude.bridge.router import ChannelRouter
from irclaude.db import connect, init_schema
from irclaude.models import Project
from irclaude.services.memory_service import MemoryService


def _memory(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    return MemoryService(conn)


@pytest.mark.asyncio
async def test_idle_close_invokes_summary_prompt_in_spanish(tmp_path):
    mem = _memory(tmp_path)
    proj = mem.upsert_project(Project(name="Foo", path=str(tmp_path)))
    sess = mem.start_session(proj.id)
    router = ChannelRouter(memory=mem)
    router.channels_for_known_projects()

    captured: list[tuple[str, str]] = []

    async def runner(channel: str, prompt: str) -> None:
        captured.append((channel, prompt))
        mem.save_summary(sess.id, "resumen final")

    router.set_runner(runner)
    router.bind_session("#foo", sess.id)
    await router.idle_close("#foo", poll_interval=0.05, max_wait=2.0)
    assert captured
    assert "resumen" in captured[0][1].lower() or "guarda" in captured[0][1].lower()


@pytest.mark.asyncio
async def test_idle_close_marks_session_closed(tmp_path):
    mem = _memory(tmp_path)
    proj = mem.upsert_project(Project(name="Foo", path=str(tmp_path)))
    sess = mem.start_session(proj.id)
    router = ChannelRouter(memory=mem)
    router.channels_for_known_projects()

    async def runner(channel: str, prompt: str) -> None:
        mem.save_summary(sess.id, "ok")

    router.set_runner(runner)
    router.bind_session("#foo", sess.id)
    await router.idle_close("#foo", poll_interval=0.05, max_wait=2.0)
    refreshed = mem.get_session(sess.id)
    assert refreshed.status.value == "closed"


@pytest.mark.asyncio
async def test_idle_close_times_out_when_summary_never_lands(tmp_path):
    mem = _memory(tmp_path)
    proj = mem.upsert_project(Project(name="Foo", path=str(tmp_path)))
    sess = mem.start_session(proj.id)
    router = ChannelRouter(memory=mem)
    router.channels_for_known_projects()

    async def runner(channel: str, prompt: str) -> None:
        await asyncio.sleep(0)

    router.set_runner(runner)
    router.bind_session("#foo", sess.id)
    await router.idle_close("#foo", poll_interval=0.05, max_wait=0.3)
    refreshed = mem.get_session(sess.id)
    assert refreshed.status.value == "closed"
