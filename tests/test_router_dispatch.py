import asyncio

import pytest

from myorch.bridge.router import ChannelRouter, SessionContext
from myorch.db import connect, init_schema
from myorch.models import Project
from myorch.services.memory_service import MemoryService


@pytest.fixture
def memory(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    return MemoryService(conn)


@pytest.mark.asyncio
async def test_start_session_returns_context(memory, tmp_path):
    mem = memory
    mem.upsert_project(Project(name="Foo", path=str(tmp_path / "foo")))
    (tmp_path / "foo").mkdir(parents=True)
    router = ChannelRouter(memory=mem)
    router.channels_for_known_projects()
    ctx = router.start_session("#foo")
    assert isinstance(ctx, SessionContext)
    assert ctx.project.name == "Foo"
    assert ctx.session_id > 0
    assert len(ctx.claude_uuid) == 36


@pytest.mark.asyncio
async def test_dispatch_message_serializes_per_channel(memory, tmp_path):
    mem = memory
    mem.upsert_project(Project(name="Foo", path=str(tmp_path / "foo")))
    (tmp_path / "foo").mkdir(parents=True)
    router = ChannelRouter(memory=mem)
    router.channels_for_known_projects()

    seen: list[str] = []

    async def fake_runner(channel: str, text: str) -> None:
        seen.append(text)
        await asyncio.sleep(0.05)

    router.set_runner(fake_runner)
    await router.dispatch_message("#foo", "first")
    await router.dispatch_message("#foo", "second")
    await router.dispatch_message("#foo", "third")
    await router.drain("#foo")
    assert seen == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_dispatch_unknown_channel_is_noop(memory):
    router = ChannelRouter(memory=memory)
    router.channels_for_known_projects()
    router.set_runner(lambda c, t: asyncio.sleep(0))
    await router.dispatch_message("#nonsense", "ping")
