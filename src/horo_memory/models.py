from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .security import SAFE_ID


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictModel(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class WorkspaceCreate(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("Use letters, numbers, dots, underscores, or hyphens")
        return value


class AgentCreate(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    runtime: str = Field(default="generic", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "workspace_id")
    @classmethod
    def safe_ids(cls, value: str) -> str:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("Invalid identifier")
        return value


class RunCreate(StrictModel):
    id: str | None = None
    workspace_id: str
    agent_id: str | None = None
    objective: str = Field(min_length=1, max_length=2000)
    workflow_version: str | None = Field(default=None, max_length=200)
    skill_versions: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "workspace_id", "agent_id")
    @classmethod
    def safe_ids(cls, value: str | None) -> str | None:
        if value is not None and not SAFE_ID.fullmatch(value):
            raise ValueError("Invalid identifier")
        return value


class RunComplete(StrictModel):
    status: Literal["completed", "failed", "cancelled"] = "completed"
    summary: str | None = Field(default=None, max_length=4000)


class EntityRef(StrictModel):
    type: str = Field(min_length=1, max_length=80)
    id: str = Field(min_length=1, max_length=256)
    label: str | None = Field(default=None, max_length=300)


class EventCreate(StrictModel):
    id: str | None = None
    workspace_id: str
    run_id: str | None = None
    actor_type: Literal["agent", "human", "system", "tool"] = "agent"
    actor_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=100)
    occurred_at: str = Field(default_factory=utc_now)
    subject: EntityRef | None = None
    object: EntityRef | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "workspace_id", "run_id")
    @classmethod
    def safe_ids(cls, value: str | None) -> str | None:
        if value is not None and not SAFE_ID.fullmatch(value):
            raise ValueError("Invalid identifier")
        return value

    @field_validator("event_type")
    @classmethod
    def normalized_event_type(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_")
        if not SAFE_ID.fullmatch(normalized):
            raise ValueError("Invalid event_type")
        return normalized


class NoteCreate(StrictModel):
    workspace_id: str
    category: Literal[
        "objectives", "campaigns", "prospects", "decisions", "learnings", "skills", "runs"
    ]
    slug: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=200_000)
    frontmatter: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workspace_id", "slug")
    @classmethod
    def safe_ids(cls, value: str) -> str:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("Invalid identifier")
        return value


class ImprovementCreate(StrictModel):
    id: str | None = None
    workspace_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10_000)
    target_type: Literal["skill", "workflow", "prompt", "policy", "other"]
    target_id: str = Field(min_length=1, max_length=300)
    based_on_event_ids: list[str] = Field(min_length=1, max_length=100)
    proposed_patch: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("id", "workspace_id")
    @classmethod
    def safe_ids(cls, value: str | None) -> str | None:
        if value is not None and not SAFE_ID.fullmatch(value):
            raise ValueError("Invalid identifier")
        return value


class ImprovementDecision(StrictModel):
    decision: Literal["approved", "rejected"]
    decided_by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=4000)


class ContextSearch(StrictModel):
    workspace_id: str
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("workspace_id")
    @classmethod
    def safe_workspace(cls, value: str) -> str:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("Invalid identifier")
        return value
