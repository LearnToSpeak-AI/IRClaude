from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    active = "active"
    closed = "closed"
    crashed = "crashed"


class Project(BaseModel):
    id: int | None = None
    name: str
    path: str
    type: str | None = None
    dev_command: str | None = None
    dev_port: int | None = None
    description: str | None = None
    last_session_id: str | None = None
    created_at: datetime | None = None
    last_opened_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    id: int | None = None
    project_id: int
    claude_session_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: str | None = None
    files_touched: list[str] = Field(default_factory=list)
    status: SessionStatus = SessionStatus.active


class Decision(BaseModel):
    id: int | None = None
    project_id: int
    session_id: int | None = None
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class Recall(BaseModel):
    id: int | None = None
    project_id: int
    text: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class GlobalPreference(BaseModel):
    id: int | None = None
    key: str
    value: str
    note: str | None = None


class SessionBrief(BaseModel):
    id: int
    started_at: datetime
    ended_at: datetime | None
    summary: str | None
    status: SessionStatus


class RecallHit(BaseModel):
    origin: str
    score: float
    snippet: str
