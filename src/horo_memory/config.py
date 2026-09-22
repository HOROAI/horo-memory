from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HORO_", env_file=".env", extra="ignore")

    api_token: str = Field(default="", min_length=0)
    data_dir: Path = Path("data")
    host: str = "127.0.0.1"
    port: int = 8088
    allowed_origins: list[str] = []
    trust_proxy: bool = False
    graphify_enabled: bool = True
    graphify_command: str = "graphify"
    max_request_bytes: int = 2 * 1024 * 1024
    dev_mode: bool = False

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def ensure_paths(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "vault").mkdir(exist_ok=True)
        (self.data_dir / "graphify-out").mkdir(exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_paths()
    return settings

