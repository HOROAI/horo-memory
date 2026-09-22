from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    runtime TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id)
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id TEXT,
    objective TEXT NOT NULL,
    workflow_version TEXT,
    skill_versions_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed','cancelled')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_workspace_started
ON runs(workspace_id, started_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    subject_type TEXT,
    subject_id TEXT,
    subject_label TEXT,
    object_type TEXT,
    object_id TEXT,
    object_label TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    payload_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_workspace_time
ON events(workspace_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_run_time
ON events(run_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_subject
ON events(workspace_id, subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_events_object
ON events(workspace_id, object_type, object_id);

CREATE TRIGGER IF NOT EXISTS events_are_immutable_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS events_are_immutable_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are immutable');
END;

CREATE TABLE IF NOT EXISTS vault_notes (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, category, slug)
);

CREATE TABLE IF NOT EXISTS improvement_proposals (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    based_on_event_ids_json TEXT NOT NULL,
    proposed_patch_json TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    status TEXT NOT NULL CHECK (status IN ('proposed','approved','rejected')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    decision_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_proposals_workspace_created
ON improvement_proposals(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS asset_versions (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('skill','workflow','prompt','policy')),
    asset_id TEXT NOT NULL,
    version TEXT NOT NULL,
    title TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '{}',
    source_ref TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, asset_type, asset_id, version)
);

CREATE TABLE IF NOT EXISTS version_evaluations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    baseline_version TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    metric TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('maximize','minimize')),
    minimum_sample_size INTEGER NOT NULL,
    baseline_result_json TEXT NOT NULL,
    candidate_result_json TEXT NOT NULL,
    delta REAL,
    improvement_percent REAL,
    verdict TEXT NOT NULL CHECK (verdict IN ('candidate_better','baseline_better','inconclusive')),
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluations_workspace_created
ON version_evaluations(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS version_releases (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    from_version TEXT,
    to_version TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('bootstrap','promote','rollback')),
    evaluation_id TEXT REFERENCES version_evaluations(id),
    proposal_id TEXT REFERENCES improvement_proposals(id),
    actor TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_releases_asset_created
ON version_releases(workspace_id, asset_type, asset_id, created_at DESC);

CREATE TRIGGER IF NOT EXISTS asset_versions_are_immutable_update BEFORE UPDATE ON asset_versions
BEGIN SELECT RAISE(ABORT, 'asset versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS asset_versions_are_immutable_delete BEFORE DELETE ON asset_versions
BEGIN SELECT RAISE(ABORT, 'asset versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_are_immutable_update BEFORE UPDATE ON version_evaluations
BEGIN SELECT RAISE(ABORT, 'evaluations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_are_immutable_delete BEFORE DELETE ON version_evaluations
BEGIN SELECT RAISE(ABORT, 'evaluations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS releases_are_immutable_update BEFORE UPDATE ON version_releases
BEGIN SELECT RAISE(ABORT, 'releases are immutable'); END;
CREATE TRIGGER IF NOT EXISTS releases_are_immutable_delete BEFORE DELETE ON version_releases
BEGIN SELECT RAISE(ABORT, 'releases are immutable'); END;
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
            if "workflow_id" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN workflow_id TEXT")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [decode_row(dict(row)) for row in rows]

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return decode_row(dict(row)) if row else None


JSON_COLUMNS = {
    "metadata_json",
    "skill_versions_json",
    "evidence_json",
    "metrics_json",
    "payload_json",
    "based_on_event_ids_json",
    "proposed_patch_json",
    "content_json",
    "baseline_result_json",
    "candidate_result_json",
}


def decode_row(row: dict[str, Any]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in row.items():
        if key in JSON_COLUMNS:
            decoded[key.removesuffix("_json")] = json.loads(value or "{}")
        else:
            decoded[key] = value
    return decoded


def encode_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
