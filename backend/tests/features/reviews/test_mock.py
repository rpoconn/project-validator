from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import wait_none

from src.features.projects import service as projects_service
from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import ProjectCreate
from src.features.reviews.anthropic_provider import AnthropicReviewProvider
from src.features.reviews.mock import MOCK_FAIL_MARKER, create_mock_client, get_mock_client
from src.features.reviews.service import get_review_provider, run_review
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
        provider_factory=lambda _: AnthropicReviewProvider(client, "claude-mock"),
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


def test_review_provider_uses_shared_mock_client_when_enabled() -> None:
    provider = get_review_provider(Settings(_env_file=None, llm_mock=True))

    assert isinstance(provider, AnthropicReviewProvider)
    assert provider.client is get_mock_client()
