from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

from fastapi import Header, HTTPException, status

from .config import Settings, get_settings

SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def require_token(authorization: str | None = Header(default=None)) -> None:
    verify_token(get_settings(), authorization)


def verify_token(settings: Settings, authorization: str | None) -> None:
    if settings.dev_mode and not settings.api_token:
        return
    if not settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HORO_API_TOKEN is not configured",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    valid = scheme.lower() == "bearer" and hmac.compare_digest(supplied, settings.api_token)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_id(value: str, label: str = "identifier") -> str:
    if not SAFE_ID.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def safe_child(root: Path, *parts: str) -> Path:
    for part in parts:
        validate_id(part, "path component")
    candidate = root.joinpath(*parts).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("Path escapes configured root")
    return candidate


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
