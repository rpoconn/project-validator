from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src import main
from src.features.projects import service as projects_service
from src.features.projects.models import ReviewStatus
from src.features.projects.schemas import ProjectCreate
from src.shared.config import Settings
from tests.features.projects.factories import project_payload


def _use_test_database(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Point the lifespan at the test database (already initialised by the fixtures)."""

    async def init_db() -> None:
        pass

    monkeypatch.setattr(main, "init_db", init_db)
    monkeypatch.setattr(main, "session_factory", session_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)


# --- lifespan -----------------------------------------------------------------------------------


async def test_lifespan_resets_reviews_interrupted_by_a_restart(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _use_test_database(monkeypatch, session_factory, Settings(_env_file=None, llm_mock=True))
    project = await projects_service.create_project(
        session, ProjectCreate.model_validate(project_payload())
    )

    async with main.lifespan(FastAPI()):
        await session.refresh(project)
        assert project.review_status is ReviewStatus.UNREVIEWED


@pytest.mark.parametrize(
    ("settings", "level", "message"),
    [
        (
            Settings(_env_file=None, llm_mock=True, anthropic_api_key=SecretStr("sk")),
            "WARNING",
            "LLM_MOCK is enabled; AI reviews are canned",
        ),
        (
            Settings(_env_file=None),
            "WARNING",
            "ANTHROPIC_API_KEY is not configured; AI reviews will fail",
        ),
        (
            Settings(_env_file=None, llm_provider="openai"),
            "WARNING",
            "OPENAI_API_KEY is not configured; AI reviews will fail",
        ),
        (
            Settings(_env_file=None, openai_api_key=SecretStr("sk")),
            "INFO",
            "AI reviews use the openai API",
        ),
        (
            Settings(_env_file=None, anthropic_api_key=SecretStr("sk")),
            "INFO",
            "AI reviews use the anthropic API",
        ),
    ],
    ids=["mock", "anthropic-missing-key", "openai-missing-key", "openai", "anthropic"],
)
async def test_lifespan_logs_how_reviews_will_run(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    settings: Settings,
    level: str,
    message: str,
) -> None:
    _use_test_database(monkeypatch, session_factory, settings)

    with caplog.at_level("INFO", logger="src.main"):
        async with main.lifespan(FastAPI()):
            pass

    [record] = [r for r in caplog.records if r.name == "src.main"]
    assert record.levelname == level
    assert message in record.getMessage()


# --- create_app ---------------------------------------------------------------------------------


async def _preflight(app: FastAPI, origin: str) -> dict[str, Any]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/projects",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
    return dict(response.headers)


async def test_create_app_allows_only_configured_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, cors_origins=["http://allowed.test"])
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    app = main.create_app()

    allowed = await _preflight(app, "http://allowed.test")
    assert allowed["access-control-allow-origin"] == "http://allowed.test"
    assert "POST" in allowed["access-control-allow-methods"]

    denied = await _preflight(app, "http://other.test")
    assert "access-control-allow-origin" not in denied


def test_create_app_uses_handler_names_as_operation_ids() -> None:
    spec = main.create_app().openapi()

    assert spec["paths"]["/api/projects"]["get"]["operationId"] == "list_projects"
    assert spec["paths"]["/api/health"]["get"]["operationId"] == "get_health"
