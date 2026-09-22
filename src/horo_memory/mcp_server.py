from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .models import (
    ContextSearch,
    EntityRef,
    EventCreate,
    ImprovementCreate,
    NoteCreate,
    RunComplete,
    RunCreate,
)
from .runtime import build_service

mcp = FastMCP("HORO Memory")
service = build_service()


def workspace() -> str:
    value = os.getenv("HORO_MCP_WORKSPACE", "")
    if not value:
        raise ValueError("HORO_MCP_WORKSPACE must be configured for the MCP server")
    return value


@mcp.tool()
def horo_context_search(query: str, limit: int = 12) -> str:
    """Search the shared HORO vault and operational event memory."""
    results = service.search_context(
        ContextSearch(workspace_id=workspace(), query=query, limit=limit)
    )
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def horo_run_start(
    objective: str,
    agent_id: str | None = None,
    workflow_version: str | None = None,
    skill_versions: dict[str, str] | None = None,
) -> str:
    """Start a traceable agent run before performing operational work."""
    run = service.start_run(
        RunCreate(
            workspace_id=workspace(),
            agent_id=agent_id,
            objective=objective,
            workflow_version=workflow_version,
            skill_versions=skill_versions or {},
        )
    )
    return json.dumps(run, ensure_ascii=False, indent=2)


@mcp.tool()
def horo_action_record(
    run_id: str,
    event_type: str,
    actor_id: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
    subject_label: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    object_label: str | None = None,
    evidence: dict[str, Any] | None = None,
    metrics: dict[str, float | int | str | None] | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Append an immutable action or outcome event with provenance."""
    subject = (
        EntityRef(type=subject_type, id=subject_id, label=subject_label)
        if subject_type and subject_id
        else None
    )
    object_ref = (
        EntityRef(type=object_type, id=object_id, label=object_label)
        if object_type and object_id
        else None
    )
    event = service.record_event(
        EventCreate(
            workspace_id=workspace(),
            run_id=run_id,
            actor_type="agent",
            actor_id=actor_id,
            event_type=event_type,
            subject=subject,
            object=object_ref,
            evidence=evidence or {},
            metrics=metrics or {},
            payload=payload or {},
        )
    )
    return json.dumps(event, ensure_ascii=False, indent=2)


@mcp.tool()
def horo_outcome_record(
    run_id: str,
    actor_id: str,
    outcome_id: str,
    label: str,
    metrics: dict[str, float | int | str | None] | None = None,
    evidence: dict[str, Any] | None = None,
) -> str:
    """Record a measured run outcome using the same immutable event ledger."""
    return horo_action_record(
        run_id=run_id,
        event_type="outcome_observed",
        actor_id=actor_id,
        object_type="outcome",
        object_id=outcome_id,
        object_label=label,
        metrics=metrics,
        evidence=evidence,
    )


@mcp.tool()
def horo_note_write(
    category: str,
    slug: str,
    title: str,
    body: str,
    frontmatter: dict[str, Any] | None = None,
) -> str:
    """Write a portable Markdown note into the workspace's Obsidian-compatible vault."""
    note = service.write_note(
        NoteCreate(
            workspace_id=workspace(),
            category=category,  # type: ignore[arg-type]
            slug=slug,
            title=title,
            body=body,
            frontmatter=frontmatter or {},
        )
    )
    return json.dumps(note, ensure_ascii=False, indent=2)


@mcp.tool()
def horo_graph_snapshot(include_graphify: bool = True) -> str:
    """Return the current operational and knowledge graph for the configured workspace."""
    graph = service.graph(workspace(), include_graphify=include_graphify)
    return json.dumps(graph, ensure_ascii=False, indent=2)


@mcp.tool()
def horo_run_complete(run_id: str, status: str = "completed", summary: str | None = None) -> str:
    """Close a run with a terminal status and concise summary."""
    run = service.complete_run(
        workspace(), run_id, RunComplete(status=status, summary=summary)  # type: ignore[arg-type]
    )
    return json.dumps(run, ensure_ascii=False, indent=2)


@mcp.tool()
def horo_improvement_propose(
    title: str,
    description: str,
    target_type: str,
    target_id: str,
    based_on_event_ids: list[str],
    proposed_patch: dict[str, Any] | None = None,
    confidence: float = 0.5,
) -> str:
    """Propose a versioned change backed by recorded events; never promotes it automatically."""
    proposal = service.create_improvement(
        ImprovementCreate(
            workspace_id=workspace(),
            title=title,
            description=description,
            target_type=target_type,  # type: ignore[arg-type]
            target_id=target_id,
            based_on_event_ids=based_on_event_ids,
            proposed_patch=proposed_patch or {},
            confidence=confidence,
        )
    )
    return json.dumps(proposal, ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
