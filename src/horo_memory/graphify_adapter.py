from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .security import safe_child


class GraphifyAdapter:
    def __init__(self, vault_root: Path, output_root: Path, command: str, enabled: bool):
        self.vault_root = vault_root
        self.output_root = output_root
        self.command = command
        self.enabled = enabled

    def status(self) -> dict[str, Any]:
        credential_names = (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "MOONSHOT_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "AWS_PROFILE",
            "AWS_ACCESS_KEY_ID",
            "OLLAMA_BASE_URL",
        )
        headless_ready = any(os.environ.get(name) for name in credential_names) or bool(shutil.which("claude"))
        return {
            "enabled": self.enabled,
            "available": bool(shutil.which(self.command)),
            "headless_ready": headless_ready,
            "assistant_managed_supported": True,
            "command": self.command,
        }

    def reindex(self, workspace_id: str) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Graphify integration is disabled")
        executable = shutil.which(self.command)
        if not executable:
            raise RuntimeError("Graphify executable is not installed")
        source = safe_child(self.vault_root, workspace_id)
        destination = safe_child(self.output_root, workspace_id)
        destination.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [executable, "extract", str(source), "--out", str(destination)],
            cwd=str(source),
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-4000:] or result.stdout[-4000:])
        return {
            "workspace_id": workspace_id,
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
        }

    def load_graph(self, workspace_id: str) -> dict[str, Any] | None:
        candidates = [
            safe_child(self.output_root, workspace_id) / "graphify-out" / "graph.json",
            safe_child(self.vault_root, workspace_id) / "graphify-out" / "graph.json",
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
        return None
