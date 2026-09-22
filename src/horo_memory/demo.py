from __future__ import annotations

import sqlite3

from .models import (
    AgentCreate,
    AssetVersionCreate,
    EntityRef,
    EventCreate,
    ImprovementCreate,
    NoteCreate,
    RunComplete,
    RunCreate,
    VersionCompareRequest,
    WorkspaceCreate,
)
from .service import ConflictError, MemoryService


def seed_demo(service: MemoryService, workspace_id: str = "horo-demo") -> dict[str, str]:
    run_ids = [f"{workspace_id}-run-{index:03d}" for index in range(1, 4)]
    event_ids = [f"{workspace_id}-evt-{index:03d}" for index in range(1, 7)]
    improvement_id = f"{workspace_id}-imp-001"
    try:
        service.create_workspace(
            WorkspaceCreate(id=workspace_id, name=f"HORO Learning · {workspace_id}")
        )
    except ConflictError:
        pass

    for version, title, initial in [
        ("1.1.0", "Apertura genérica de automatización", True),
        ("1.2.0", "Apertura basada en fricción verificable", False),
    ]:
        try:
            service.register_version(
                AssetVersionCreate(
                    workspace_id=workspace_id,
                    asset_type="skill",
                    asset_id="linkedin-prospecting",
                    version=version,
                    title=title,
                    content={"opening_strategy": title},
                    source_ref="vault://skills/linkedin-prospecting.md",
                    created_by="demo-operator",
                    set_as_initial=initial,
                )
            )
        except ConflictError:
            pass

    try:
        service.create_agent(
            AgentCreate(
                id="hermes-sales",
                workspace_id=workspace_id,
                name="Hermes Ventas",
                runtime="hermes",
                metadata={"role": "prospecting-agent"},
            )
        )
    except ConflictError:
        pass

    service.write_note(
        NoteCreate(
            workspace_id=workspace_id,
            category="skills",
            slug="linkedin-prospecting",
            title="LinkedIn Prospecting",
            body=(
                "## Purpose\n\nCreate relevant conversations with observable evidence.\n\n"
                "## Production version\n\n`1.1.0`\n\n"
                "## Candidate version\n\n`1.2.0`\n\n"
                "## Rule\n\nLead with a concrete operational problem and one short question."
            ),
            frontmatter={"version": "1.2.0", "status": "candidate"},
        )
    )

    runs = [
        (run_ids[0], "Validar mensaje centrado en automatización", "1.1.0"),
        (run_ids[1], "Validar mensaje centrado en seguimiento", "1.2.0"),
        (run_ids[2], "Comparar respuesta de empresas mineras", "1.2.0"),
    ]
    for run_id, objective, skill_version in runs:
        try:
            service.start_run(
                RunCreate(
                    id=run_id,
                    workspace_id=workspace_id,
                    agent_id="hermes-sales",
                    objective=objective,
                    workflow_id="commercial-learning-loop",
                    workflow_version="commercial-loop-v1",
                    skill_versions={"linkedin-prospecting": skill_version},
                )
            )
        except ConflictError:
            pass

    events = [
        EventCreate(
            id=event_ids[0],
            workspace_id=workspace_id,
            run_id=run_ids[0],
            actor_type="agent",
            actor_id="hermes-sales",
            event_type="message_drafted",
            occurred_at="2026-09-18T14:12:00Z",
            subject=EntityRef(type="prospect", id="andes-supply", label="Andes Supply"),
            object=EntityRef(type="campaign", id="mining-cl-v1", label="Minería Chile v1"),
            evidence={"artifact": "campaigns/mining-cl-v1.md"},
            metrics={"human_edits": 4, "duration_seconds": 96},
        ),
        EventCreate(
            id=event_ids[1],
            workspace_id=workspace_id,
            run_id=run_ids[0],
            actor_type="human",
            actor_id="operator",
            event_type="message_rejected",
            occurred_at="2026-09-18T14:18:00Z",
            subject=EntityRef(type="campaign", id="mining-cl-v1", label="Minería Chile v1"),
            object=EntityRef(type="outcome", id="review-001", label="Demasiado genérico"),
            evidence={"reason": "No menciona una fricción operacional verificable"},
        ),
        EventCreate(
            id=event_ids[2],
            workspace_id=workspace_id,
            run_id=run_ids[1],
            actor_type="agent",
            actor_id="hermes-sales",
            event_type="message_sent",
            occurred_at="2026-09-19T14:20:00Z",
            subject=EntityRef(type="prospect", id="norte-industrial", label="Norte Industrial"),
            object=EntityRef(type="campaign", id="followup-angle", label="Ángulo seguimiento"),
            evidence={"channel": "linkedin", "receipt": "simulated-demo-002"},
            metrics={"human_edits": 1, "duration_seconds": 48},
        ),
        EventCreate(
            id=event_ids[3],
            workspace_id=workspace_id,
            run_id=run_ids[1],
            actor_type="system",
            actor_id="linkedin-monitor",
            event_type="positive_reply",
            occurred_at="2026-09-19T18:34:00Z",
            subject=EntityRef(type="prospect", id="norte-industrial", label="Norte Industrial"),
            object=EntityRef(type="outcome", id="reply-002", label="Solicita información"),
            evidence={"message_id": "simulated-reply-002", "classification": "interest"},
            metrics={"reply": 1, "hours_to_reply": 4.2},
        ),
        EventCreate(
            id=event_ids[4],
            workspace_id=workspace_id,
            run_id=run_ids[2],
            actor_type="agent",
            actor_id="hermes-sales",
            event_type="pattern_observed",
            occurred_at="2026-09-20T16:02:00Z",
            subject=EntityRef(
                type="skill",
                id="linkedin-prospecting",
                label="LinkedIn Prospecting",
            ),
            object=EntityRef(
                type="outcome",
                id="pattern-followup",
                label="Seguimiento supera automatización",
            ),
            evidence={"event_ids": [event_ids[1], event_ids[3]]},
            metrics={"sample_size": 2, "confidence": 0.58},
        ),
        EventCreate(
            id=event_ids[5],
            workspace_id=workspace_id,
            run_id=run_ids[2],
            actor_type="agent",
            actor_id="hermes-sales",
            event_type="message_drafted",
            occurred_at="2026-09-20T15:42:00Z",
            subject=EntityRef(type="prospect", id="cobre-servicios", label="Cobre Servicios"),
            object=EntityRef(type="campaign", id="mining-cl-v2", label="Minería Chile v2"),
            evidence={"artifact": "campaigns/mining-cl-v2.md"},
            metrics={"human_edits": 2, "duration_seconds": 61},
        ),
    ]
    for event in events:
        service.record_event(event)

    for run_id, _, _ in runs:
        try:
            service.complete_run(
                workspace_id,
                run_id,
                RunComplete(status="completed", summary="Ejecución demostrativa registrada"),
            )
        except ConflictError:
            pass

    try:
        service.create_improvement(
            ImprovementCreate(
                id=improvement_id,
                workspace_id=workspace_id,
                title="Priorizar fricción de seguimiento",
                description=(
                    "La variante específica necesitó menos correcciones y produjo una "
                    "respuesta positiva. "
                    "Requiere más observaciones antes de promoverse."
                ),
                target_type="skill",
                target_id="linkedin-prospecting",
                based_on_event_ids=[event_ids[1], event_ids[3], event_ids[4]],
                proposed_patch={
                    "from": "hablar de automatización general",
                    "to": "abrir con una fricción de seguimiento verificable",
                },
                confidence=0.58,
            )
        )
    except (sqlite3.IntegrityError, ConflictError):
        pass
    if not service.list_evaluations(workspace_id):
        service.compare_versions(
            VersionCompareRequest(
                workspace_id=workspace_id,
                asset_type="skill",
                asset_id="linkedin-prospecting",
                baseline_version="1.1.0",
                candidate_version="1.2.0",
                metric="human_edits",
                direction="minimize",
                minimum_sample_size=1,
            )
        )
    return {"workspace_id": workspace_id, "status": "ready"}
