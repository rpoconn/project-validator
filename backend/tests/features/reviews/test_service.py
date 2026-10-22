from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import openai
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import wait_none

from src.features.projects import service as projects_service
from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import ProjectCreate, ProjectReview
from src.features.reviews import service as reviews_service
from src.features.reviews.anthropic_provider import AnthropicReviewProvider
from src.features.reviews.openai_provider import OpenAIReviewProvider
from src.features.reviews.provider import ReviewProvider, ReviewRefusedError
from src.features.reviews.schemas import ReviewPrompt
from src.features.reviews.service import (
    MAX_EXISTING_PROJECTS,
    describe_error,
    get_review_provider,
    is_retryable,
    request_review,
    run_review,
)
from src.shared.config import Settings
from src.shared.llm_clients import LLMNotConfiguredError
from tests.features.projects.factories import project_payload
from tests.features.reviews.fakes import (
    VALID_REVIEW,
    ScriptedEndpoint,
    api_error,
    make_message,
    make_response,
    scripted_anthropic,
    scripted_openai,
)

PROMPT = ReviewPrompt(system="system", user_message="user")
SETTINGS = Settings(_env_file=None, llm_max_attempts=3)
_REQUEST = httpx2.Request("POST", "https://api.example.test/v1/messages")

type Scripted = Callable[..., tuple[ReviewProvider, ScriptedEndpoint]]
# (scripted provider factory, canned-response factory, SDK module) for each provider.
PROVIDERS = [
    pytest.param(scripted_anthropic, make_message, anthropic, id="anthropic"),
    pytest.param(scripted_openai, make_response, openai, id="openai"),
]


# --- error classification -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (api_error(anthropic.RateLimitError, 429), True),
        (api_error(anthropic.InternalServerError, 500), True),
        (api_error(anthropic.OverloadedError, 529), True),
        (anthropic.APIConnectionError(request=_REQUEST), True),
        (anthropic.APITimeoutError(request=_REQUEST), True),
        (api_error(anthropic.AuthenticationError, 401), False),
        (api_error(anthropic.BadRequestError, 400), False),
        (api_error(anthropic.PermissionDeniedError, 403), False),
        (api_error(openai.RateLimitError, 429), True),
        (api_error(openai.InternalServerError, 500), True),
        (api_error(openai.ConflictError, 409), True),
        (openai.APIConnectionError(request=_REQUEST), True),
        (openai.APITimeoutError(request=_REQUEST), True),
        (api_error(openai.AuthenticationError, 401), False),
        (api_error(openai.BadRequestError, 400), False),
        (api_error(openai.PermissionDeniedError, 403), False),
        (LLMNotConfiguredError("ANTHROPIC_API_KEY"), False),
        (ValueError("bug"), False),
    ],
)
def test_is_retryable(error: Exception, retryable: bool) -> None:
    assert is_retryable(error) is retryable


@pytest.mark.parametrize("sdk", [anthropic, openai])
def test_describe_error_includes_type_message_and_request_id(sdk: Any) -> None:
    error = api_error(sdk.AuthenticationError, 401, "invalid api key", "req_123")

    assert describe_error(error) == "AuthenticationError: invalid api key (request_id=req_123)"


def test_describe_error_without_request_id() -> None:
    assert describe_error(LLMNotConfiguredError("OPENAI_API_KEY")) == (
        "LLMNotConfiguredError: OPENAI_API_KEY not configured"
    )
    assert describe_error(RuntimeError()) == "RuntimeError: no details"


# --- request_review -----------------------------------------------------------------------------


async def _request(provider: ReviewProvider, max_attempts: int = 3) -> ProjectReview:
    return await request_review(provider, PROMPT, max_attempts=max_attempts, wait=wait_none())


@pytest.mark.parametrize(("scripted", "make_ok", "sdk"), PROVIDERS)
async def test_request_review_retries_transient_errors(
    monkeypatch: pytest.MonkeyPatch, scripted: Scripted, make_ok: Callable[..., Any], sdk: Any
) -> None:
    provider, script = scripted(
        monkeypatch, api_error(sdk.RateLimitError, 429), make_ok("not json"), make_ok()
    )

    review = await _request(provider)

    assert review == ProjectReview.model_validate(VALID_REVIEW)
    assert len(script.calls) == 3


@pytest.mark.parametrize(("scripted", "make_ok", "sdk"), PROVIDERS)
async def test_request_review_gives_up_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch, scripted: Scripted, make_ok: Callable[..., Any], sdk: Any
) -> None:
    provider, script = scripted(
        monkeypatch, *(api_error(sdk.InternalServerError, 500, "overloaded") for _ in range(3))
    )

    with pytest.raises(sdk.InternalServerError):
        await _request(provider)

    assert len(script.calls) == 3


@pytest.mark.parametrize(
    ("scripted", "outcome", "expected"),
    [
        (scripted_anthropic, api_error(anthropic.AuthenticationError, 401), None),
        (scripted_anthropic, api_error(anthropic.BadRequestError, 400), None),
        (scripted_anthropic, api_error(anthropic.PermissionDeniedError, 403), None),
        (scripted_anthropic, make_message("", stop_reason="refusal"), ReviewRefusedError),
        (scripted_openai, api_error(openai.AuthenticationError, 401), None),
        (scripted_openai, api_error(openai.BadRequestError, 400), None),
        (scripted_openai, make_response(refusal="No."), ReviewRefusedError),
    ],
)
async def test_request_review_does_not_retry_permanent_failures(
    monkeypatch: pytest.MonkeyPatch,
    scripted: Scripted,
    outcome: Any,
    expected: type[Exception] | None,
) -> None:
    provider, script = scripted(monkeypatch, outcome)

    with pytest.raises(expected or type(outcome)):
        await _request(provider)

    assert len(script.calls) == 1


# --- get_review_provider ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (Settings(_env_file=None, llm_provider="anthropic"), AnthropicReviewProvider),
        (Settings(_env_file=None, llm_provider="openai"), OpenAIReviewProvider),
        # The offline mock fakes the Anthropic API whichever provider is configured.
        (Settings(_env_file=None, llm_provider="openai", llm_mock=True), AnthropicReviewProvider),
    ],
)
def test_get_review_provider_follows_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, expected: type
) -> None:
    monkeypatch.setattr(
        reviews_service, "get_anthropic_client", lambda: anthropic.AsyncAnthropic(api_key="sk")
    )
    monkeypatch.setattr(
        reviews_service, "get_openai_client", lambda: openai.AsyncOpenAI(api_key="sk")
    )

    assert isinstance(get_review_provider(settings), expected)


# --- run_review ---------------------------------------------------------------------------------


async def _create(session: AsyncSession, **overrides: Any) -> Project:
    return await projects_service.create_project(
        session, ProjectCreate.model_validate(project_payload(**overrides))
    )


async def _run(
    project_id: int,
    session_factory: async_sessionmaker[AsyncSession],
    provider: ReviewProvider,
) -> None:
    await run_review(
        project_id,
        session_factory,
        provider_factory=lambda _: provider,
        settings=SETTINGS,
        wait=wait_none(),
    )


@pytest.mark.parametrize(("scripted", "make_ok", "sdk"), PROVIDERS)
async def test_run_review_stores_review_and_compares_with_other_projects(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    scripted: Scripted,
    make_ok: Callable[..., Any],
    sdk: Any,
) -> None:
    await _create(session, title="Existing cold-chain upgrade")
    project = await _create(session, title="New robotics pilot")
    provider, script = scripted(monkeypatch, make_ok())

    await _run(project.id, session_factory, provider)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.COMPLETE
    assert project.review == VALID_REVIEW
    assert project.review_error is None
    [call] = script.calls
    user_message = call["messages"][0]["content"] if sdk is anthropic else call["input"]
    new_part, existing_part = user_message.split("<existing_projects")
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
    provider, script = scripted_anthropic(monkeypatch, make_message())

    await _run(project.id, session_factory, provider)

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
    provider, script = scripted_anthropic(
        monkeypatch, api_error(anthropic.RateLimitError, 429), make_message()
    )

    await _run(project.id, session_factory, provider)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.COMPLETE
    assert len(script.calls) == 2


async def test_run_review_records_persistent_server_error(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project = await _create(session)
    provider, script = scripted_anthropic(
        monkeypatch,
        *(
            api_error(anthropic.InternalServerError, 500, "internal error", "req_500")
            for _ in range(3)
        ),
    )

    await _run(project.id, session_factory, provider)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error == "InternalServerError: internal error (request_id=req_500)"
    assert project.review is None
    assert len(script.calls) == 3


@pytest.mark.parametrize(("scripted", "make_ok", "sdk"), PROVIDERS)
async def test_run_review_auth_error_fails_after_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    scripted: Scripted,
    make_ok: Callable[..., Any],
    sdk: Any,
) -> None:
    project = await _create(session)
    provider, script = scripted(
        monkeypatch, api_error(sdk.AuthenticationError, 401, "invalid api key", "req_401")
    )

    await _run(project.id, session_factory, provider)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error == "AuthenticationError: invalid api key (request_id=req_401)"
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
    provider, _ = scripted_anthropic(monkeypatch, refusal)

    await _run(project.id, session_factory, provider)

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
    provider, _ = scripted_anthropic(monkeypatch, api_error(anthropic.AuthenticationError, 401))

    await _run(project.id, session_factory, provider)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review is None


async def test_run_review_without_api_key_makes_no_request(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    project = await _create(session)

    def unconfigured(_: Settings) -> ReviewProvider:
        raise LLMNotConfiguredError("OPENAI_API_KEY")

    await run_review(project.id, session_factory, provider_factory=unconfigured, settings=SETTINGS)

    await session.refresh(project)
    assert project.review_status is ReviewStatus.ERROR
    assert project.review_error == "LLMNotConfiguredError: OPENAI_API_KEY not configured"


async def test_run_review_discards_outcome_when_project_deleted_mid_review(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    project = await _create(session)
    provider, script = scripted_anthropic(monkeypatch, make_message())

    async def create_then_delete(**kwargs: Any) -> Any:
        await projects_service.delete_project(session, project.id)
        return await script.create(**kwargs)

    monkeypatch.setattr(provider.client.beta.messages, "create", create_then_delete)

    with caplog.at_level("WARNING"):
        await _run(project.id, session_factory, provider)

    assert len(script.calls) == 1
    assert "deleted during its review" in caplog.text
    assert "Could not record review outcome" not in caplog.text
    assert await projects_service.list_projects(session) == []


async def test_run_review_never_raises_for_missing_project(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    provider, script = scripted_anthropic(monkeypatch)

    await _run(12345, session_factory, provider)

    assert script.calls == []
