from typing import Any

import httpx2
import pytest
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import wait_none

from src.features.projects import service as projects_service
from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import ProjectCreate, ProjectReview
from src.features.reviews.anthropic_provider import AnthropicReviewProvider
from src.features.reviews.mock import (
    MOCK_FAIL_MARKER,
    MOCK_MODEL,
    MockMessagesTransport,
    canned_review,
    create_mock_client,
    get_mock_client,
)
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


# --- canned_review and the transport, without the SDK ------------------------------------------


@pytest.mark.parametrize(
    ("count", "noun"),
    [(0, "0 existing projects"), (1, "1 existing project"), (2, "2 existing projects")],
)
def test_canned_review_pluralises_existing_projects(count: int, noun: str) -> None:
    review = canned_review("Any", count)

    assert review.summary.endswith(f"compared against {noun}.")
    assert review.risks[0].startswith(f"Portfolio overlap was not assessed: {noun} were")
    assert len(review.tags) == 3


def _messages_request(prompt: str) -> httpx2.Request:
    body = {"messages": [{"role": "user", "content": prompt}]}
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages", json=body)


async def _send(transport: MockMessagesTransport, prompt: str) -> dict[str, Any]:
    response = await transport.handle_async_request(_messages_request(prompt))
    await response.aread()
    return {"status": response.status_code, "headers": dict(response.headers), **response.json()}


async def test_transport_defaults_when_prompt_has_no_title_or_count() -> None:
    transport = MockMessagesTransport(latency_seconds=0)

    body = await _send(transport, "no tags at all")

    assert body["status"] == 200
    review = ProjectReview.model_validate_json(body["content"][0]["text"])
    assert review.summary.startswith("Mock review of “Untitled”")
    assert "compared against 0 existing projects" in review.summary


async def test_transport_unescapes_title_and_counts_requests() -> None:
    transport = MockMessagesTransport(latency_seconds=0)
    prompt = (
        "<project_input>\n<title>Clinic &lt;booking&gt; &amp; billing</title>\n"
        '</project_input>\n<existing_projects count="4">'
    )

    first = await _send(transport, prompt)
    second = await _send(transport, prompt)

    assert transport.request_count == 2
    assert first["headers"]["request-id"] == "req_mock_1"
    assert second["headers"]["request-id"] == "req_mock_2"
    assert second["id"] == "msg_mock_2"
    review = ProjectReview.model_validate_json(first["content"][0]["text"])
    assert review.summary.startswith("Mock review of “Clinic <booking> & billing”")
    assert "compared against 4 existing projects" in review.summary
    assert first["usage"] == {"input_tokens": len(prompt) // 4, "output_tokens": 100}
    assert first["model"] == MOCK_MODEL


async def test_transport_fail_marker_returns_401_once_per_title() -> None:
    transport = MockMessagesTransport(latency_seconds=0)
    prompt = f"<project_input><title>Flaky {MOCK_FAIL_MARKER}</title></project_input>"

    failed = await _send(transport, prompt)
    assert failed["status"] == 401
    assert failed["error"]["type"] == "authentication_error"
    assert failed["request_id"] == "req_mock_1"

    assert (await _send(transport, prompt))["status"] == 200
    other = f"<project_input><title>Other {MOCK_FAIL_MARKER}</title></project_input>"
    assert (await _send(transport, other))["status"] == 401


def test_get_mock_client_is_cached() -> None:
    assert get_mock_client() is get_mock_client()
    assert get_mock_client().max_retries == 0
