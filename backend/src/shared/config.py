"""Application settings loaded from environment variables and `.env` files."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files take priority: backend/.env overrides the repo-root .env.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    # Total attempts per review (first call included); retries back off exponentially with jitter.
    llm_max_attempts: int = Field(default=3, ge=1)
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    # Serve canned reviews from an offline fake of the Messages API (e2e tests and demos).
    llm_mock: bool = False
    database_url: str = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}"
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
