from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from horo_memory.api import create_app
from horo_memory.config import Settings


@pytest.fixture
def token() -> str:
    return "test-token-that-is-long-enough"


@pytest.fixture
def client(tmp_path, token: str) -> TestClient:
    settings = Settings(
        api_token=token,
        data_dir=tmp_path / "data",
        graphify_enabled=False,
        dev_mode=False,
    )
    return TestClient(create_app(settings))


@pytest.fixture
def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def workspace(client: TestClient, auth: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/workspaces",
        headers=auth,
        json={"id": "tenant-a", "name": "Tenant A"},
    )
    assert response.status_code == 201
    return response.json()

