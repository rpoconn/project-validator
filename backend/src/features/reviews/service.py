"""AI risk review: builds the prompt, calls the configured LLM with retries, records the outcome.

`run_review` is the background entry point the projects router schedules via `get_review_runner`.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import anthropic
import openai
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)
from tenacity.wait import wait_base

from src.features.projects import service as projects_service
from src.features.projects.schemas import ProjectRead, ProjectReview
from src.features.reviews.anthropic_provider import AnthropicReviewProvider
from src.features.reviews.mock import get_mock_client
from src.features.reviews.openai_provider import OpenAIReviewProvider
from src.features.reviews.prompt import build_prompt
from src.features.reviews.provider import ReviewError, ReviewProvider
from src.features.reviews.schemas import ReviewPrompt
from src.shared.config import Settings, get_settings
from src.shared.database import session_factory as default_session_factory
from src.shared.llm_clients import get_anthropic_client, get_openai_client

logger = logging.getLogger(__name__)

ReviewRunner = Callable[[int], Awaitable[None]]
ProviderFactory = Callable[[Settings], ReviewProvider]

MAX_EXISTING_PROJECTS = 50
RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})
DEFAULT_WAIT: wait_base = wait_random_exponential(multiplier=1, max=30)

API_ERRORS = (anthropic.APIError, openai.APIError)
API_STATUS_ERRORS = (anthropic.APIStatusError, openai.APIStatusError)
# Both SDKs raise their connection error for timeouts too.
API_CONNECTION_ERRORS = (anthropic.APIConnectionError, openai.APIConnectionError)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ReviewError):
        return exc.retryable
    if isinstance(exc, API_STATUS_ERRORS):
        return exc.status_code in RETRYABLE_STATUS_CODES or exc.status_code >= 500
    return isinstance(exc, API_CONNECTION_ERRORS)


def describe_error(exc: BaseException) -> str:
    """One-line, human-readable failure stored on the project for diagnosis."""
    message = exc.message if isinstance(exc, API_ERRORS) else str(exc)
    description = f"{type(exc).__name__}: {message or 'no details'}"
    request_id = exc.request_id if isinstance(exc, (*API_STATUS_ERRORS, ReviewError)) else None
    return f"{description} (request_id={request_id})" if request_id else description


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    logger.warning(
        "Review attempt %s failed, retrying: %s",
        state.attempt_number,
        describe_error(exc) if exc else "unknown error",
    )


async def request_review(
    provider: ReviewProvider,
    prompt: ReviewPrompt,
    *,
    max_attempts: int,
    wait: wait_base = DEFAULT_WAIT,
) -> ProjectReview:
    """Call the provider until a valid review comes back, retrying only transient failures."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait,
        retry=retry_if_exception(is_retryable),
        before_sleep=_log_retry,
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            return await provider.generate(prompt)
    raise AssertionError("unreachable: tenacity re-raises the last failure")


def get_review_provider(settings: Settings) -> ReviewProvider:
    """The configured provider, or the offline Anthropic mock when `LLM_MOCK` is enabled."""
    if settings.llm_mock:
        return AnthropicReviewProvider(get_mock_client(), settings.anthropic_model)
    if settings.active_llm_provider == "openai":
        return OpenAIReviewProvider(get_openai_client(), settings.openai_model)
    return AnthropicReviewProvider(get_anthropic_client(), settings.anthropic_model)


async def run_review(
    project_id: int,
    session_factory: async_sessionmaker[AsyncSession] = default_session_factory,
    *,
    provider_factory: ProviderFactory = get_review_provider,
    settings: Settings | None = None,
    wait: wait_base = DEFAULT_WAIT,
) -> None:
    """Background entry point. Opens its own sessions (the request's is closed) and never raises.

    The database session is released before calling the LLM so a slow review never holds a
    connection.
    """
    settings = settings or get_settings()
    try:
        async with session_factory() as session:
            project = ProjectRead.model_validate(
                await projects_service.get_project(session, project_id)
            )
            others = await projects_service.list_projects(
                session, limit=MAX_EXISTING_PROJECTS + 1, exclude_id=project_id
            )
        existing = [ProjectRead.model_validate(other) for other in others[:MAX_EXISTING_PROJECTS]]
        prompt = build_prompt(
            project,
            existing,
            today=datetime.now(UTC).date(),
            truncated=len(others) > MAX_EXISTING_PROJECTS,
        )
        review = await request_review(
            provider_factory(settings),
            prompt,
            max_attempts=settings.llm_max_attempts,
            wait=wait,
        )
    except projects_service.ProjectNotFoundError:
        logger.warning("Project %s disappeared before its review could run", project_id)
        return
    except Exception as exc:
        logger.exception("Review failed for project %s", project_id)
        await _record_outcome(session_factory, project_id, describe_error(exc))
        return
    await _record_outcome(session_factory, project_id, review)


async def _record_outcome(
    session_factory: async_sessionmaker[AsyncSession],
    project_id: int,
    outcome: ProjectReview | str,
) -> None:
    try:
        async with session_factory() as session:
            if isinstance(outcome, ProjectReview):
                await projects_service.set_review_result(session, project_id, outcome)
            else:
                await projects_service.set_review_error(session, project_id, outcome)
    except projects_service.ProjectNotFoundError:
        logger.warning("Project %s was deleted during its review; outcome discarded", project_id)
    except Exception:
        logger.exception("Could not record review outcome for project %s", project_id)


def get_review_runner() -> ReviewRunner:
    """FastAPI dependency so tests can swap the background review for a fake."""
    return run_review
