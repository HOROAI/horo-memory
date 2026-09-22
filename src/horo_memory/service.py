from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from .db import Database, encode_json
from .graphify_adapter import GraphifyAdapter
from .models import (
    AgentCreate,
    ContextSearch,
    EventCreate,
    ImprovementCreate,
    ImprovementDecision,
    NoteCreate,
    RunComplete,
    RunCreate,
    WorkspaceCreate,
    new_id,
    utc_now,
)
from .security import digest_bytes, safe_child
from .vault import Vault


class ConflictError(ValueError):
    pass


class NotFoundError(ValueError):
    pass


class MemoryService:
    def __init__(
        self,
        database: Database,
        vault: Vault,
        graphify: GraphifyAdapter,
    ):
        self.database = database
        self.vault = vault
        self.graphify = graphify
        self._vault_lock = threading.Lock()

    def create_workspace(self, request: WorkspaceCreate) -> dict[str, Any]:
        created_at = utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO workspaces(id, name, created_at) VALUES (?, ?, ?)",
                    (request.id, request.name, created_at),
                )
        except sqlite3.IntegrityError as error:
            raise ConflictError(f"Workspace {request.id!r} already exists") from error
        self.vault.workspace_root(request.id)
        return {"id": request.id, "name": request.name, "created_at": created_at}

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self.database.fetch_all("SELECT * FROM workspaces ORDER BY created_at")

    def create_agent(self, request: AgentCreate) -> dict[str, Any]:
        self._require_workspace(request.workspace_id)
        created_at = utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO agents(id, workspace_id, name, runtime, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.id,
                        request.workspace_id,
                        request.name,
                        request.runtime,
                        encode_json(request.metadata),
                        created_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ConflictError(f"Agent {request.id!r} already exists in this workspace") from error
        return self.get_agent(request.workspace_id, request.id)

    def get_agent(self, workspace_id: str, agent_id: str) -> dict[str, Any]:
        row = self.database.fetch_one(
            "SELECT * FROM agents WHERE workspace_id = ? AND id = ?",
            (workspace_id, agent_id),
        )
        if not row:
            raise NotFoundError("Agent not found")
        return row

    def list_agents(self, workspace_id: str) -> list[dict[str, Any]]:
        self._require_workspace(workspace_id)
        return self.database.fetch_all(
            "SELECT * FROM agents WHERE workspace_id = ? ORDER BY created_at", (workspace_id,)
        )

    def start_run(self, request: RunCreate) -> dict[str, Any]:
        self._require_workspace(request.workspace_id)
        if request.agent_id:
            self.get_agent(request.workspace_id, request.agent_id)
        run_id = request.id or new_id("run")
        started_at = utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO runs(
                        id, workspace_id, agent_id, objective, workflow_version,
                        skill_versions_json, metadata_json, status, started_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
                    """,
                    (
                        run_id,
                        request.workspace_id,
                        request.agent_id,
                        request.objective,
                        request.workflow_version,
                        encode_json(request.skill_versions),
                        encode_json(request.metadata),
                        started_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ConflictError(f"Run {run_id!r} already exists") from error
        self._initialize_run_note(run_id, request, started_at)
        return self.get_run(request.workspace_id, run_id)

    def get_run(self, workspace_id: str, run_id: str) -> dict[str, Any]:
        row = self.database.fetch_one(
            "SELECT * FROM runs WHERE workspace_id = ? AND id = ?", (workspace_id, run_id)
        )
        if not row:
            raise NotFoundError("Run not found")
        return row

    def list_runs(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        self._require_workspace(workspace_id)
        return self.database.fetch_all(
            "SELECT * FROM runs WHERE workspace_id = ? ORDER BY started_at DESC LIMIT ?",
            (workspace_id, limit),
        )

    def complete_run(
        self, workspace_id: str, run_id: str, request: RunComplete
    ) -> dict[str, Any]:
        run = self.get_run(workspace_id, run_id)
        if run["status"] != "running":
            raise ConflictError("Only a running run can be completed")
        completed_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE runs SET status = ?, completed_at = ?, summary = ?
                WHERE workspace_id = ? AND id = ?
                """,
                (request.status, completed_at, request.summary, workspace_id, run_id),
            )
        self._append_run_note(
            workspace_id,
            run_id,
            f"\n## Completion\n\n- Status: `{request.status}`\n- At: `{completed_at}`\n"
            + (f"- Summary: {request.summary}\n" if request.summary else ""),
        )
        return self.get_run(workspace_id, run_id)

    def record_event(self, request: EventCreate) -> dict[str, Any]:
        self._require_workspace(request.workspace_id)
        if request.run_id:
            self.get_run(request.workspace_id, request.run_id)
        event_id = request.id or new_id("evt")
        existing = self.database.fetch_one("SELECT * FROM events WHERE id = ?", (event_id,))
        normalized = request.model_dump(exclude={"id"}, mode="json")
        if existing and "occurred_at" not in request.model_fields_set:
            normalized["occurred_at"] = existing["occurred_at"]
        content_hash = digest_bytes(encode_json(normalized).encode("utf-8"))
        if existing:
            if existing["content_hash"] != content_hash:
                raise ConflictError("Event id already exists with different immutable content")
            return existing
        subject = request.subject
        object_ref = request.object
        created_at = utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO events(
                        id, workspace_id, run_id, actor_type, actor_id, event_type, occurred_at,
                        subject_type, subject_id, subject_label,
                        object_type, object_id, object_label,
                        evidence_json, metrics_json, payload_json, content_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        request.workspace_id,
                        request.run_id,
                        request.actor_type,
                        request.actor_id,
                        request.event_type,
                        request.occurred_at,
                        subject.type if subject else None,
                        subject.id if subject else None,
                        subject.label if subject else None,
                        object_ref.type if object_ref else None,
                        object_ref.id if object_ref else None,
                        object_ref.label if object_ref else None,
                        encode_json(request.evidence),
                        encode_json(request.metrics),
                        encode_json(request.payload),
                        content_hash,
                        created_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ConflictError("Event could not be recorded") from error
        event = self.get_event(request.workspace_id, event_id)
        if request.run_id:
            self._append_event_to_run_note(event)
        return event

    def get_event(self, workspace_id: str, event_id: str) -> dict[str, Any]:
        row = self.database.fetch_one(
            "SELECT * FROM events WHERE workspace_id = ? AND id = ?",
            (workspace_id, event_id),
        )
        if not row:
            raise NotFoundError("Event not found")
        return row

    def list_events(self, workspace_id: str, limit: int = 200) -> list[dict[str, Any]]:
        self._require_workspace(workspace_id)
        return self.database.fetch_all(
            "SELECT * FROM events WHERE workspace_id = ? ORDER BY occurred_at DESC LIMIT ?",
            (workspace_id, limit),
        )

    def write_note(self, request: NoteCreate) -> dict[str, Any]:
        self._require_workspace(request.workspace_id)
        result = self.vault.write_note(request)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO vault_notes(
                    workspace_id, category, slug, title, relative_path, sha256, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, category, slug) DO UPDATE SET
                    title = excluded.title,
                    relative_path = excluded.relative_path,
                    sha256 = excluded.sha256,
                    updated_at = excluded.updated_at
                """,
                (
                    request.workspace_id,
                    request.category,
                    request.slug,
                    request.title,
                    result["relative_path"],
                    result["sha256"],
                    result["updated_at"],
                ),
            )
        return {**request.model_dump(), **result}

    def create_improvement(self, request: ImprovementCreate) -> dict[str, Any]:
        self._require_workspace(request.workspace_id)
        placeholders = ",".join("?" for _ in request.based_on_event_ids)
        rows = self.database.fetch_all(
            f"SELECT id FROM events WHERE workspace_id = ? AND id IN ({placeholders})",
            (request.workspace_id, *request.based_on_event_ids),
        )
        found = {row["id"] for row in rows}
        missing = sorted(set(request.based_on_event_ids) - found)
        if missing:
            raise ValueError(f"Unknown evidence events: {', '.join(missing)}")
        proposal_id = request.id or new_id("imp")
        created_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO improvement_proposals(
                    id, workspace_id, title, description, target_type, target_id,
                    based_on_event_ids_json, proposed_patch_json, confidence, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)
                """,
                (
                    proposal_id,
                    request.workspace_id,
                    request.title,
                    request.description,
                    request.target_type,
                    request.target_id,
                    encode_json(request.based_on_event_ids),
                    encode_json(request.proposed_patch),
                    request.confidence,
                    created_at,
                ),
            )
        return self.get_improvement(request.workspace_id, proposal_id)

    def get_improvement(self, workspace_id: str, proposal_id: str) -> dict[str, Any]:
        row = self.database.fetch_one(
            "SELECT * FROM improvement_proposals WHERE workspace_id = ? AND id = ?",
            (workspace_id, proposal_id),
        )
        if not row:
            raise NotFoundError("Improvement proposal not found")
        return row

    def list_improvements(self, workspace_id: str) -> list[dict[str, Any]]:
        self._require_workspace(workspace_id)
        return self.database.fetch_all(
            """
            SELECT * FROM improvement_proposals
            WHERE workspace_id = ? ORDER BY created_at DESC
            """,
            (workspace_id,),
        )

    def decide_improvement(
        self, workspace_id: str, proposal_id: str, request: ImprovementDecision
    ) -> dict[str, Any]:
        proposal = self.get_improvement(workspace_id, proposal_id)
        if proposal["status"] != "proposed":
            raise ConflictError("This proposal already has a decision")
        decided_at = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE improvement_proposals
                SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?
                WHERE workspace_id = ? AND id = ?
                """,
                (
                    request.decision,
                    decided_at,
                    request.decided_by,
                    request.note,
                    workspace_id,
                    proposal_id,
                ),
            )
        return self.get_improvement(workspace_id, proposal_id)

    def search_context(self, request: ContextSearch) -> list[dict[str, Any]]:
        self._require_workspace(request.workspace_id)
        vault_matches = self.vault.search(request.workspace_id, request.query, request.limit)
        pattern = f"%{request.query}%"
        event_matches = self.database.fetch_all(
            """
            SELECT * FROM events
            WHERE workspace_id = ? AND (
                event_type LIKE ? OR actor_id LIKE ? OR subject_label LIKE ? OR object_label LIKE ?
                OR evidence_json LIKE ? OR payload_json LIKE ?
            )
            ORDER BY occurred_at DESC LIMIT ?
            """,
            (
                request.workspace_id,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                request.limit,
            ),
        )
        return (vault_matches + [{"source": "event", **row} for row in event_matches])[
            : request.limit
        ]

    def graph(self, workspace_id: str, include_graphify: bool = True) -> dict[str, Any]:
        self._require_workspace(workspace_id)
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        edge_keys: set[tuple[str, str, str]] = set()

        def node(node_id: str, kind: str, label: str, **data: Any) -> str:
            key = f"{kind}:{node_id}"
            nodes.setdefault(key, {**data, "id": key, "kind": kind, "label": label})
            return key

        def edge(source: str, target: str, relation: str, **data: Any) -> None:
            key = (source, target, relation)
            if key not in edge_keys:
                edge_keys.add(key)
                edges.append(
                    {
                        "id": f"edge:{len(edges) + 1}",
                        "source": source,
                        "target": target,
                        "relation": relation,
                        **data,
                    }
                )

        workspace = self._require_workspace(workspace_id)
        workspace_node = node(workspace_id, "workspace", workspace["name"], **workspace)
        for agent in self.list_agents(workspace_id):
            agent_node = node(agent["id"], "agent", agent["name"], **agent)
            edge(workspace_node, agent_node, "contains")
        for run in self.list_runs(workspace_id, 500):
            run_node = node(run["id"], "run", run["objective"], **run)
            edge(workspace_node, run_node, "contains")
            if run["agent_id"]:
                agent_node = node(run["agent_id"], "agent", run["agent_id"])
                edge(agent_node, run_node, "executed")
        for event in reversed(self.list_events(workspace_id, 2000)):
            event_node = node(
                event["id"],
                "event",
                event["event_type"].replace("_", " "),
                **event,
            )
            actor_node = node(
                event["actor_id"], event["actor_type"], event["actor_id"]
            )
            edge(actor_node, event_node, "performed")
            if event["run_id"]:
                edge(f"run:{event['run_id']}", event_node, "recorded")
            if event["subject_type"] and event["subject_id"]:
                subject_node = node(
                    event["subject_id"],
                    event["subject_type"],
                    event["subject_label"] or event["subject_id"],
                )
                edge(event_node, subject_node, "subject")
            if event["object_type"] and event["object_id"]:
                object_node = node(
                    event["object_id"],
                    event["object_type"],
                    event["object_label"] or event["object_id"],
                )
                edge(event_node, object_node, event["event_type"])
        for proposal in self.list_improvements(workspace_id):
            proposal_node = node(
                proposal["id"], "improvement", proposal["title"], **proposal
            )
            target_node = node(
                proposal["target_id"], proposal["target_type"], proposal["target_id"]
            )
            edge(proposal_node, target_node, "proposes_change_to")
            for event_id in proposal["based_on_event_ids"]:
                edge(f"event:{event_id}", proposal_node, "supports")

        graphify_loaded = False
        if include_graphify:
            graphify_loaded = self._merge_graphify(workspace_id, nodes, edges, edge_keys)
        return {
            "workspace_id": workspace_id,
            "generated_at": utc_now(),
            "graphify_loaded": graphify_loaded,
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    def stats(self, workspace_id: str) -> dict[str, Any]:
        self._require_workspace(workspace_id)
        result: dict[str, Any] = {}
        for name, table in [
            ("agents", "agents"),
            ("runs", "runs"),
            ("events", "events"),
            ("proposals", "improvement_proposals"),
        ]:
            row = self.database.fetch_one(
                f"SELECT COUNT(*) AS count FROM {table} WHERE workspace_id = ?",
                (workspace_id,),
            )
            result[name] = row["count"] if row else 0
        result["pending_proposals"] = (
            self.database.fetch_one(
                """
                SELECT COUNT(*) AS count FROM improvement_proposals
                WHERE workspace_id = ? AND status = 'proposed'
                """,
                (workspace_id,),
            )
            or {"count": 0}
        )["count"]
        return result

    def _require_workspace(self, workspace_id: str) -> dict[str, Any]:
        row = self.database.fetch_one("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        if not row:
            raise NotFoundError(f"Workspace {workspace_id!r} not found")
        return row

    def _initialize_run_note(self, run_id: str, request: RunCreate, started_at: str) -> None:
        note = NoteCreate(
            workspace_id=request.workspace_id,
            category="runs",
            slug=run_id,
            title=f"Run {run_id}",
            body=(
                f"## Objective\n\n{request.objective}\n\n"
                f"## Configuration\n\n"
                f"- Agent: `{request.agent_id or 'unassigned'}`\n"
                f"- Workflow version: `{request.workflow_version or 'unspecified'}`\n"
                f"- Skill versions: `{json.dumps(request.skill_versions, ensure_ascii=False)}`\n"
                f"- Started: `{started_at}`\n\n"
                "## Events\n"
            ),
            frontmatter={"run_id": run_id, "status": "running"},
        )
        self.write_note(note)

    def _append_event_to_run_note(self, event: dict[str, Any]) -> None:
        parts = [
            f"\n- `{event['occurred_at']}` **{event['event_type']}** by "
            f"`{event['actor_type']}:{event['actor_id']}`"
        ]
        if event["subject_type"] and event["subject_id"]:
            parts.append(f"  - Subject: `{event['subject_type']}:{event['subject_id']}`")
        if event["object_type"] and event["object_id"]:
            parts.append(f"  - Object: `{event['object_type']}:{event['object_id']}`")
        if event["evidence"]:
            parts.append(f"  - Evidence: `{json.dumps(event['evidence'], ensure_ascii=False)}`")
        self._append_run_note(event["workspace_id"], event["run_id"], "\n".join(parts) + "\n")

    def _append_run_note(self, workspace_id: str, run_id: str, content: str) -> None:
        workspace_root = self.vault.workspace_root(workspace_id)
        path = safe_child(workspace_root, "runs") / f"{run_id}.md"
        with self._vault_lock:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(content)

    def _merge_graphify(
        self,
        workspace_id: str,
        nodes: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
        edge_keys: set[tuple[str, str, str]],
    ) -> bool:
        raw = self.graphify.load_graph(workspace_id)
        if not raw:
            return False
        raw_nodes = raw.get("nodes", []) if isinstance(raw, dict) else []
        raw_edges = raw.get("edges", raw.get("links", [])) if isinstance(raw, dict) else []
        for item in raw_nodes:
            if isinstance(item, str):
                raw_id, label, data = item, item, {}
            elif isinstance(item, dict):
                raw_id = str(item.get("id", item.get("name", "")))
                label = str(item.get("label", item.get("name", raw_id)))
                data = item
            else:
                continue
            if raw_id:
                nodes.setdefault(
                    f"knowledge:{raw_id}",
                    {
                        "id": f"knowledge:{raw_id}",
                        "kind": "knowledge",
                        "label": label,
                        "source": "graphify",
                        "graphify": data,
                    },
                )
        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", item.get("from", "")))
            target = str(item.get("target", item.get("to", "")))
            relation = str(item.get("relation", item.get("type", "related")))
            key = (f"knowledge:{source}", f"knowledge:{target}", relation)
            if source and target and key not in edge_keys:
                edge_keys.add(key)
                edges.append(
                    {
                        "id": f"edge:{len(edges) + 1}",
                        "source": key[0],
                        "target": key[1],
                        "relation": relation,
                        "source_system": "graphify",
                    }
                )
        return True
