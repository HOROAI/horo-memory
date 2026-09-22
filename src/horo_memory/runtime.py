from __future__ import annotations

from .config import Settings, get_settings
from .db import Database
from .graphify_adapter import GraphifyAdapter
from .service import MemoryService
from .vault import Vault


def build_service(settings: Settings | None = None) -> MemoryService:
    settings = settings or get_settings()
    settings.ensure_paths()
    vault_root = settings.data_dir / "vault"
    graphify_root = settings.data_dir / "graphify-out"
    return MemoryService(
        database=Database(settings.data_dir / "horo-memory.sqlite3"),
        vault=Vault(vault_root),
        graphify=GraphifyAdapter(
            vault_root=vault_root,
            output_root=graphify_root,
            command=settings.graphify_command,
            enabled=settings.graphify_enabled,
        ),
    )

