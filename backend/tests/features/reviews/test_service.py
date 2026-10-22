import json
from typing import Any

import httpx2
import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OverloadedError,
    PermissionDeniedError,
    RateLimitError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import wait_none

from src.features.projects import service as projects_service
from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import ProjectCreate, ProjectReview
from src.features.reviews.schemas import ReviewPrompt
from src.features.reviews.service import (
    FALLBACK_BETA,
    MAX_EXISTING_PROJECTS,
    MalformedReviewError,
    ReviewRefusedError,
    describe_error,
    is_retryable,
    parse_review,
    request_review,
    run_review,
)
from src.shared.anthropic_client import AnthropicNotConfiguredError
from src.shared.config import Settings
from tests.features.projects.factories import project_payload
from tests.features.reviews.fakes import (
    VALID_REVIEW,
    api_error,
    make_message,
    scripted_client,
)

PROMPT = ReviewPrompt(system="system", user_message="user")
SETTINGS = Settings(_env_file=None, llm_max_attempts=3)
_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


# --- parse_review -------------------------------------------------------------------------------


def test_parse_review_success() -> None:
    assert parse_review(make_message()) == ProjectReview.model_validate(VALID_REVIEW)


def test_parse_review_refusal_is_not_retryable() -> None:
    message = make_message(
        "",
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": "cyber", "explanation": "Declined."},
        request_id="req_refused",
    )

    with pytest.raises(ReviewRefusedError) as excinfo:
        parse_review(message)

    assert str(excinfo.value) == (
        "Claude declined to review this project (category=cyber): Declined."
    )
    assert excinfo.value.request_id == "req_refused"
    assert not is_retryable(excinfo.value)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (make_message('{"summary": "cut', stop_reason="max_tokens"), "output token limit"),
        (make_message(""), "no review text"),
        (make_message("not json"), "did not match the expected format"),
        (
            make_message(json.dumps({**VALID_REVIEW, "tags": ["a", "A", "b"]})),
            "tags: Value error, tags must contain 3 distinct",
        ),
    ],
)
def test_parse_review_malformed_output_is_retryable(message: Any, expected: str) -> None:
    with pytest.raises(MalformedReviewError, match=expected) as excinfo:
        parse_review(message)

    assert excinfo.value.request_id == "req_ok"
    assert is_retryable(excinfo.value)


# --- error classification -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (api_error(RateLimitError, 429), True),
        (api_error(InternalServerError, 500), True),
        (api_error(OverloadedError, 529), True),
        (APIConnectionError(request=_REQUEST), True),
        (APITimeoutError(request=_REQUEST), True),
        (api_error(AuthenticationError, 401), False),
        (api_error(BadRequestError, 400), False),
        (api_error(PermissionDeniedError, 403), False),
        (AnthropicNotConfiguredError(), False),
        (ValueError("bug"), False),
    ],
)
def test_is_retryable(error: Exception, retryable: bool) -> None:
    assert is_retryable(error) is retryable


def test_describe_error_includes_type_message_and_request_id() -> None:
    assert (
        describe_error(api_error(AuthenticationError, 401, "invalid x-api-key", "req_123"))
        == "AuthenticationError: invalid x-api-key (request_id=req_123)"
    )
    assert describe_error(AnthropicNotConfiguredError()) == (
        "AnthropicNotConfiguredError: ANTHROPIC_API_KEY not configured"
    )
    assert describe_error(RuntimeError()) == "RuntimeError: no details"


# --- request_review -----------------------------------------------------------------------------


async def _request(client: AsyncAnthropic, max_attempts: int = 3) -> ProjectReview:
    return await request_review(
        client, PROMPT, model="claude-sonnet-5-5", max_attempts=max_attempts, wait=wait_none()
    )


async def test_request_review_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client, script = scripted_client(monkeypatch, make_message())

    review = await _request(client)

    assert review.tags == VALID_REVIEW["tags"]
    [call] = script.calls
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"] == "system"
    assert call["messages"] == [{"role": "user", "content": "user"}]
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert set(call["output_config"]["format"]["schema"]["properties"]) == {
        "summary",
        "tags",
        "risks",
    }
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert "thinking" not in call


async def test_request_review_retries_transient_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client, script = scripted_client(
        monkeypatch,
        api_error(RateLimitError, 429),
        make_message("not json"),
        make_message(),
    )

    review = await _request(client)

    assert review == ProjectReview.model_validate(VALID_REVIEW)
    assert len(script.calls) == 3


async def test_request_review_gives_up_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, script = scripted_client(
        monkeypatch, *(api_error(InternalServerError, 500, "overloaded") for _ in range(3))
    )

    with pytest.raises(InternalServerError):
        await _request(client)

    assert len(script.calls) == 3


@pytest.mark.parametrize(
    "outcome",
    [
        api_error(AuthenticationError, 401),
        api_error(BadRequestError, 400),
        api_error(PermissionDeniedError, 403),
        make_message("", stop_reason="refusal"),
    ],
)
async def test_request_review_does_not_retry_permanent_failures(
    monkeypatch: pytest.MonkeyPatch, outcome: Any
) -> None:
    client, script = scripted_client(monkeypatch, outcome, make_message())

    with pytest.raises(type(outcome) if isinstance(outcome, Exception) else ReviewRefusedError):
        await _request(client)

    assert len(script.calls) == 1


# --- run_review ---------------------------------------------------------------------------------


async def _create(session: AsyncSession, **overrides: Any) -> Project:
    return await projects_service.create_project(
        session, ProjectCreate.model_validate(project_payload(**overrides))
    )


async def _run(
    project_id: int,
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncAnthropic,
) -> None:
    await run_review(
        project_id,
        session_factory,
        client_factory=lambda: client,
        settings=SETTINGS,
        wait=wait_none(),
    )


async def test_run_review_stores_review_and_compares_with_other_projects(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create(session, title="Existing cold-chain upgrade")
    project = await _create(session, title="New robotics pilot")
    client, script = scripted_client(monkeypatch, make_message())

    await _run(project.id, session_factory, client)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.COMPLETE
    assert project.review == VALID_REVIEW
    assert project.review_error is None
    new_part, existing_part = script.calls[0]["messages"][0]["content"].split("<existing_projects")
    assert "<title>New robotics pilot</title>" in new_part
    assert "<title>Existing cold-chain upgrade</title>" in existing_part


async def test_run_review_caps_existing_projects(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    for index in range(MAX_EXISTING_PROJECTS + 1):
        await _create(session, title=f"Other {index}")
    project = await _create(session)
    client, script = scripted_client(monkeypatch, make_message())

    await _run(project.id, session_factory, client)

    user_message = script.calls[0]["messages"][0]["content"]
    assert user_message.count("<existing_project id=") == MAX_EXISTING_PROJECTS
    assert "<title>Other 0</title>" not in user_message  # the oldest one is dropped
    assert "older projects exist but were omitted" in user_message


async def test_run_review_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project = await _create(session)
    client, script = scripted_client(monkeypatch, api_error(RateLimitError, 429), make_message())

    await _run(project.id, session_factory, client)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.COMPLETE
    assert len(script.calls) == 2


async def test_run_review_records_persistent_server_error(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project = await _create(session)
    client, script = scripted_client(
        monkeypatch,
        *(api_error(InternalServerError, 500, "internal error", "req_500") for _ in range(3)),
    )

    await _run(project.id, session_factory, client)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error == "InternalServerError: internal error (request_id=req_500)"
    assert project.review is None
    assert len(script.calls) == 3


async def test_run_review_auth_error_fails_after_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project = await _create(session)
    client, script = scripted_client(
        monkeypatch, api_error(AuthenticationError, 401, "invalid x-api-key", "req_401")
    )

    await _run(project.id, session_factory, client)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error == "AuthenticationError: invalid x-api-key (request_id=req_401)"
    assert len(script.calls) == 1


async def test_run_review_refusal_records_error(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project = await _create(session)
    refusal = make_message(
        "",
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": None, "explanation": None},
        request_id="req_refused",
    )
    client, _ = scripted_client(monkeypatch, refusal)

    await _run(project.id, session_factory, client)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error == (
        "ReviewRefusedError: Claude declined to review this project (category=unspecified) "
        "(request_id=req_refused)"
    )


async def test_run_review_wipes_previous_review_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project = await _create(session)
    await projects_service.set_review_result(
        session, project.id, ProjectReview.model_validate(VALID_REVIEW)
    )
    await projects_service.mark_review_pending(session, project.id)
    client, _ = scripted_client(monkeypatch, api_error(AuthenticationError, 401))

    await _run(project.id, session_factory, client)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review is None


async def test_run_review_without_api_key_makes_no_request(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    project = await _create(session)

    def unconfigured() -> AsyncAnthropic:
        raise AnthropicNotConfiguredError()

    await run_review(project.id, session_factory, client_factory=unconfigured, settings=SETTINGS)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error == "AnthropicNotConfiguredError: ANTHROPIC_API_KEY not configured"


async def test_run_review_discards_outcome_when_project_deleted_mid_review(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    project = await _create(session)
    client, script = scripted_client(monkeypatch, make_message())

    async def create_then_delete(**kwargs: Any) -> Any:
        await projects_service.delete_project(session, project.id)
        return await script.create(**kwargs)

    monkeypatch.setattr(client.beta.messages, "create", create_then_delete)

    with caplog.at_level("WARNING"):
        await _run(project.id, session_factory, client)

    assert len(script.calls) == 1
    assert "deleted during its review" in caplog.text
    assert "Could not record review outcome" not in caplog.text
    assert await projects_service.list_projects(session) == []


async def test_run_review_never_raises_for_missing_project(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    client, script = scripted_client(monkeypatch)

    await _run(12345, session_factory, client)

    assert script.calls == []
