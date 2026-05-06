import re
from typing import Iterable

from myorch.models import Project
from myorch.services.memory_service import MemoryService


_NON_CHAN = re.compile(r"[^a-z0-9-]")
_DASH_RUN = re.compile(r"-+")


def project_to_channel(name: str) -> str:
    lowered = name.lower()
    cleaned = _NON_CHAN.sub("-", lowered)
    cleaned = _DASH_RUN.sub("-", cleaned).strip("-")
    if not cleaned:
        cleaned = "project"
    cleaned = cleaned[:49]
    return "#" + cleaned


def _disambiguate(channels: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for chan in channels:
        if chan not in seen:
            seen[chan] = 1
            out.append(chan)
            continue
        seen[chan] += 1
        out.append(f"{chan}-{seen[chan]}")
    return out


class ChannelRouter:
    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory
        self._cache: dict[str, Project] = {}

    def channels_for_known_projects(self) -> list[str]:
        projects = self.memory.list_projects()
        chans = [project_to_channel(p.name) for p in projects]
        out = _disambiguate(chans)
        self._cache = {c: p for c, p in zip(out, projects)}
        return out

    def project_for_channel(self, channel: str) -> Project | None:
        if not self._cache:
            self.channels_for_known_projects()
        return self._cache.get(channel)
