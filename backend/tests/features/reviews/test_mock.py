from typing import Any

import pytest
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import wait_none

from src.features.projects import service as projects_service
from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import ProjectCreate
from src.features.reviews import service as reviews_service
from src.features.reviews.mock import MOCK_FAIL_MARKER, create_mock_client, get_mock_client
from src.features.reviews.service import get_review_client, run_review
from src.shared.config import Settings
from tests.features.projects.factories import project_payload

SETTINGS = Settings(_env_file=None, llm_max_attempts=3)


async def _create(session: AsyncSession, **overrides: Any) -> Project:
    return await projects_service.create_project(
        session, ProjectCreate.model_validate(project_payload(**overrides))
    )


async def _run(
    project: Project,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncAnthropic,
) -> Project:
    """Run the review and return the project as stored afterwards."""
    await run_review(
        project.id,
        session_factory,
        client_factory=lambda: client,
        settings=SETTINGS,
        wait=wait_none(),
    )
    await session.refresh(project)
    return project


async def test_mock_review_names_project_and_counts_portfolio(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _create(session, title="Existing project")
    project = await _create(session, title="Clinic <booking> & billing")

    project = await _run(project, session, session_factory, create_mock_client(latency_seconds=0))

    assert project.review_status is ReviewStatus.COMPLETE
    assert project.review is not None
    assert project.review["summary"].startswith("Mock review of “Clinic <booking> & billing”")
    assert "compared against 1 existing project." in project.review["summary"]
    assert project.review["tags"] == ["mock review", "offline", "deterministic"]
    assert len(project.review["risks"]) == 2


async def test_mock_fail_marker_fails_first_review_then_succeeds(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    project = await _create(session, title=f"Flaky {MOCK_FAIL_MARKER}")
    client = create_mock_client(latency_seconds=0)

    project = await _run(project, session, session_factory, client)

    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error is not None
    assert project.review_error.startswith("AuthenticationError: Error code: 401")
    assert "Mock failure for titles containing [mock-fail]" in project.review_error
    assert project.review_error.endswith("(request_id=req_mock_1)")

    await projects_service.mark_review_pending(session, project.id)
    project = await _run(project, session, session_factory, client)

    assert project.review_status is ReviewStatus.COMPLETE
    assert project.review_error is None


async def test_marker_in_existing_project_does_not_fail_new_review(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _create(session, title=f"Old {MOCK_FAIL_MARKER}")
    project = await _create(session, title="New project")

    project = await _run(project, session, session_factory, create_mock_client(latency_seconds=0))

    assert project.review_status is ReviewStatus.COMPLETE


@pytest.mark.parametrize("llm_mock", [True, False])
def test_review_client_follows_llm_mock_setting(
    monkeypatch: pytest.MonkeyPatch, llm_mock: bool
) -> None:
    real_client = AsyncAnthropic(api_key="sk-test")
    monkeypatch.setattr(
        reviews_service, "get_settings", lambda: Settings(_env_file=None, llm_mock=llm_mock)
    )
    monkeypatch.setattr(reviews_service, "get_anthropic_client", lambda: real_client)

    client = get_review_client()

    assert (client is get_mock_client()) is llm_mock
    assert (client is real_client) is not llm_mock
