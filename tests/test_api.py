from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_is_public_and_security_headers_exist(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_protected_endpoints_require_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_complete_operational_memory_cycle(
    client: TestClient, auth: dict[str, str], workspace: dict
) -> None:
    agent = client.post(
        "/api/v1/agents",
        headers=auth,
        json={
            "id": "hermes-horo",
            "workspace_id": workspace["id"],
            "name": "Hermes HORO",
            "runtime": "hermes",
        },
    )
    assert agent.status_code == 201

    run = client.post(
        "/api/v1/runs",
        headers=auth,
        json={
            "id": "run-001",
            "workspace_id": workspace["id"],
            "agent_id": "hermes-horo",
            "objective": "Conseguir una reunión calificada",
            "workflow_version": "sales-v1",
            "skill_versions": {"prospecting": "1.0.0"},
        },
    )
    assert run.status_code == 201

    event = client.post(
        "/api/v1/events",
        headers=auth,
        json={
            "id": "evt-001",
            "workspace_id": workspace["id"],
            "run_id": "run-001",
            "actor_type": "agent",
            "actor_id": "hermes-horo",
            "event_type": "positive_reply",
            "subject": {"type": "prospect", "id": "lead-1", "label": "Empresa Uno"},
            "object": {"type": "outcome", "id": "reply-1", "label": "Respuesta positiva"},
            "evidence": {"source": "linkedin", "message_id": "msg-7"},
            "metrics": {"reply": 1},
        },
    )
    assert event.status_code == 201
    assert event.json()["evidence"]["message_id"] == "msg-7"

    proposal = client.post(
        "/api/v1/improvements",
        headers=auth,
        json={
            "id": "imp-001",
            "workspace_id": workspace["id"],
            "title": "Conservar el ángulo de seguimiento",
            "description": "La respuesta positiva utilizó este ángulo.",
            "target_type": "skill",
            "target_id": "prospecting",
            "based_on_event_ids": ["evt-001"],
            "proposed_patch": {"angle": "seguimiento"},
            "confidence": 0.65,
        },
    )
    assert proposal.status_code == 201
    assert proposal.json()["status"] == "proposed"

    decision = client.post(
        "/api/v1/workspaces/tenant-a/improvements/imp-001/decision",
        headers=auth,
        json={"decision": "approved", "decided_by": "operator"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    graph = client.get("/api/v1/graph?workspace_id=tenant-a", headers=auth)
    assert graph.status_code == 200
    node_ids = {node["id"] for node in graph.json()["nodes"]}
    assert "run:run-001" in node_ids
    assert "event:evt-001" in node_ids
    assert "improvement:imp-001" in node_ids

    completed = client.post(
        "/api/v1/workspaces/tenant-a/runs/run-001/complete",
        headers=auth,
        json={"status": "completed", "summary": "Resultado registrado"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_event_ids_are_immutable_and_idempotent(
    client: TestClient, auth: dict[str, str], workspace: dict
) -> None:
    payload = {
        "id": "evt-fixed",
        "workspace_id": workspace["id"],
        "actor_id": "agent-1",
        "event_type": "observation",
        "payload": {"value": 1},
    }
    first = client.post("/api/v1/events", headers=auth, json=payload)
    repeated = client.post("/api/v1/events", headers=auth, json=payload)
    conflicting = client.post(
        "/api/v1/events", headers=auth, json={**payload, "payload": {"value": 2}}
    )
    assert first.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json()["content_hash"] == first.json()["content_hash"]
    assert conflicting.status_code == 409


def test_workspace_isolation_applies_to_evidence(
    client: TestClient, auth: dict[str, str], workspace: dict
) -> None:
    client.post(
        "/api/v1/events",
        headers=auth,
        json={
            "id": "evt-private",
            "workspace_id": workspace["id"],
            "actor_id": "agent-a",
            "event_type": "observation",
        },
    )
    client.post(
        "/api/v1/workspaces", headers=auth, json={"id": "tenant-b", "name": "Tenant B"}
    )
    proposal = client.post(
        "/api/v1/improvements",
        headers=auth,
        json={
            "workspace_id": "tenant-b",
            "title": "Invalid cross-tenant evidence",
            "description": "Must be rejected",
            "target_type": "skill",
            "target_id": "x",
            "based_on_event_ids": ["evt-private"],
        },
    )
    assert proposal.status_code == 400
    assert "Unknown evidence events" in proposal.json()["detail"]


def test_ids_cannot_escape_the_vault(
    client: TestClient, auth: dict[str, str], workspace: dict
) -> None:
    response = client.post(
        "/api/v1/runs",
        headers=auth,
        json={
            "id": "../outside",
            "workspace_id": workspace["id"],
            "objective": "Attempt path traversal",
        },
    )
    assert response.status_code == 422


def test_version_evaluation_promotion_and_rollback(
    client: TestClient, auth: dict[str, str], workspace: dict
) -> None:
    for version, initial in [("1.0.0", True), ("1.1.0", False)]:
        response = client.post(
            "/api/v1/versions",
            headers=auth,
            json={
                "workspace_id": workspace["id"],
                "asset_type": "skill",
                "asset_id": "sales-message",
                "version": version,
                "title": f"Sales message {version}",
                "content": {"version": version},
                "created_by": "operator",
                "set_as_initial": initial,
            },
        )
        assert response.status_code == 201

    for run_id, version, edits in [
        ("run-base", "1.0.0", 5),
        ("run-candidate", "1.1.0", 2),
    ]:
        assert client.post(
            "/api/v1/runs",
            headers=auth,
            json={
                "id": run_id,
                "workspace_id": workspace["id"],
                "objective": "Draft a relevant message",
                "skill_versions": {"sales-message": version},
            },
        ).status_code == 201
        assert client.post(
            "/api/v1/events",
            headers=auth,
            json={
                "id": f"evt-{run_id}",
                "workspace_id": workspace["id"],
                "run_id": run_id,
                "actor_id": "agent",
                "event_type": "message_reviewed",
                "metrics": {"human_edits": edits},
            },
        ).status_code == 201

    evaluation = client.post(
        "/api/v1/evaluations/compare",
        headers=auth,
        json={
            "workspace_id": workspace["id"],
            "asset_type": "skill",
            "asset_id": "sales-message",
            "baseline_version": "1.0.0",
            "candidate_version": "1.1.0",
            "metric": "human_edits",
            "direction": "minimize",
        },
    )
    assert evaluation.status_code == 201
    assert evaluation.json()["verdict"] == "candidate_better"
    assert evaluation.json()["improvement_percent"] == 60

    proposal = client.post(
        "/api/v1/improvements",
        headers=auth,
        json={
            "workspace_id": workspace["id"],
            "title": "Use the lower-edit message",
            "description": "It required fewer human edits.",
            "target_type": "skill",
            "target_id": "sales-message",
            "based_on_event_ids": ["evt-run-base", "evt-run-candidate"],
        },
    ).json()
    client.post(
        f"/api/v1/workspaces/{workspace['id']}/improvements/{proposal['id']}/decision",
        headers=auth,
        json={"decision": "approved", "decided_by": "operator"},
    )
    promoted = client.post(
        f"/api/v1/workspaces/{workspace['id']}/assets/skill/sales-message/"
        "versions/1.1.0/promote",
        headers=auth,
        json={
            "evaluation_id": evaluation.json()["id"],
            "proposal_id": proposal["id"],
            "promoted_by": "operator",
        },
    )
    assert promoted.status_code == 201
    assert promoted.json()["to_version"] == "1.1.0"

    rolled_back = client.post(
        f"/api/v1/workspaces/{workspace['id']}/assets/skill/sales-message/rollback",
        headers=auth,
        json={"release_id": promoted.json()["id"], "rolled_back_by": "operator"},
    )
    assert rolled_back.status_code == 201
    assert rolled_back.json()["action"] == "rollback"
    assert rolled_back.json()["to_version"] == "1.0.0"
