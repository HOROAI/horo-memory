from __future__ import annotations

import sqlite3
import subprocess

import pytest

from horo_memory.db import Database
from horo_memory.graphify_adapter import GraphifyAdapter


def test_event_rows_cannot_be_updated_or_deleted(tmp_path) -> None:
    database = Database(tmp_path / "memory.sqlite3")
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO workspaces(id, name, created_at) VALUES ('w', 'Workspace', 'now')"
        )
        connection.execute(
            """
            INSERT INTO events(
                id, workspace_id, actor_type, actor_id, event_type, occurred_at,
                evidence_json, metrics_json, payload_json, content_hash, created_at
            ) VALUES ('e', 'w', 'agent', 'a', 'observed', 'now', '{}', '{}', '{}', 'x', 'now')
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="events are immutable"):
        with database.transaction() as connection:
            connection.execute("UPDATE events SET event_type = 'changed' WHERE id = 'e'")

    with pytest.raises(sqlite3.IntegrityError, match="events are immutable"):
        with database.transaction() as connection:
            connection.execute("DELETE FROM events WHERE id = 'e'")


def test_graphify_uses_supported_headless_extract_command(tmp_path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    source = vault / "workspace-a"
    source.mkdir(parents=True)
    output = tmp_path / "output"
    captured: dict[str, object] = {}

    monkeypatch.setattr("horo_memory.graphify_adapter.shutil.which", lambda _: "/bin/graphify")

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="indexed", stderr="")

    monkeypatch.setattr("horo_memory.graphify_adapter.subprocess.run", fake_run)
    adapter = GraphifyAdapter(vault, output, "graphify", enabled=True)
    result = adapter.reindex("workspace-a")

    assert captured["command"] == [
        "/bin/graphify",
        "extract",
        str(source.resolve()),
        "--out",
        str((output / "workspace-a").resolve()),
    ]
    assert captured["kwargs"]["shell"] is False  # type: ignore[index]
    assert result["returncode"] == 0
