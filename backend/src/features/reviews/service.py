"""AI risk review: builds the prompt, calls Claude with retries, and records the outcome.

`run_review` is the background entry point the projects router schedules via `get_review_runner`.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Final

from anthropic import APIConnectionError, APIError, APIStatusError, AsyncAnthropic, transform_schema
from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaOutputConfigParam
from pydantic import ValidationError
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
from src.features.reviews.mock import get_mock_client
from src.features.reviews.prompt import build_prompt
from src.features.reviews.schemas import ReviewPrompt
from src.shared.anthropic_client import get_anthropic_client
from src.shared.config import Settings, get_settings
from src.shared.database import session_factory as default_session_factory

logger = logging.getLogger(__name__)

ReviewRunner = Callable[[int], Awaitable[None]]

MAX_EXISTING_PROJECTS = 50
MAX_OUTPUT_TOKENS = 16_000
EFFORT: Final = "medium"
# Policy declines are re-run server-side on Anthropic's recommended fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})
DEFAULT_WAIT: wait_base = wait_random_exponential(multiplier=1, max=30)

OUTPUT_CONFIG: BetaOutputConfigParam = {
    "effort": EFFORT,
    "format": {"type": "json_schema", "schema": transform_schema(ProjectReview)},
}


class ReviewError(Exception):
    """A review attempt failed for a reason other than an API error."""

    retryable = False

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id


class ReviewRefusedError(ReviewError):
    """Claude (and its fallback) declined the request. Retrying would decline again."""


class MalformedReviewError(ReviewError):
    """The response was truncated, empty or did not match `ProjectReview`."""

    retryable = True


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ReviewError):
        return exc.retryable
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUS_CODES or exc.status_code >= 500
    return isinstance(exc, APIConnectionError)  # includes APITimeoutError


def describe_error(exc: BaseException) -> str:
    """One-line, human-readable failure stored on the project for diagnosis."""
    message = exc.message if isinstance(exc, APIError) else str(exc)
    description = f"{type(exc).__name__}: {message or 'no details'}"
    request_id = exc.request_id if isinstance(exc, APIStatusError | ReviewError) else None
    return f"{description} (request_id={request_id})" if request_id else description


def parse_review(response: BetaMessage) -> ProjectReview:
    request_id = response._request_id
    if response.stop_reason == "refusal":
        details = response.stop_details
        category = (details.category if details else None) or "unspecified"
        explanation = f": {details.explanation}" if details and details.explanation else ""
        raise ReviewRefusedError(
            f"Claude declined to review this project (category={category}){explanation}",
            request_id=request_id,
        )
    if response.stop_reason == "max_tokens":
        raise MalformedReviewError(
            "Review was cut off at the output token limit", request_id=request_id
        )
    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise MalformedReviewError("Response contained no review text", request_id=request_id)
    try:
        return ProjectReview.model_validate_json(text)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "response"
        raise MalformedReviewError(
            f"Review did not match the expected format ({location}: {first['msg']})",
            request_id=request_id,
        ) from exc


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    logger.warning(
        "Review attempt %s failed, retrying: %s",
        state.attempt_number,
        describe_error(exc) if exc else "unknown error",
    )


async def request_review(
    client: AsyncAnthropic,
    prompt: ReviewPrompt,
    *,
    model: str,
    max_attempts: int,
    wait: wait_base = DEFAULT_WAIT,
) -> ProjectReview:
    """Call Claude until a valid review comes back, retrying only transient failures."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait,
        retry=retry_if_exception(is_retryable),
        before_sleep=_log_retry,
        reraise=True,
    )
    messages: list[BetaMessageParam] = [{"role": "user", "content": prompt.user_message}]
    async for attempt in retrying:
        with attempt:
            response = await client.beta.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=prompt.system,
                messages=messages,
                output_config=OUTPUT_CONFIG,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            review = parse_review(response)
            logger.info(
                "Review generated by %s (request_id=%s, input_tokens=%s, output_tokens=%s)",
                response.model,
                response._request_id,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return review
    raise AssertionError("unreachable: tenacity re-raises the last failure")


def get_review_client() -> AsyncAnthropic:
    """The shared Anthropic client, or the offline mock when `LLM_MOCK` is enabled."""
    return get_mock_client() if get_settings().llm_mock else get_anthropic_client()


async def run_review(
    project_id: int,
    session_factory: async_sessionmaker[AsyncSession] = default_session_factory,
    *,
    client_factory: Callable[[], AsyncAnthropic] = get_review_client,
    settings: Settings | None = None,
    wait: wait_base = DEFAULT_WAIT,
) -> None:
    """Background entry point. Opens its own sessions (the request's is closed) and never raises.

    The database session is released before calling Claude so a slow review never holds a
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
            client_factory(),
            prompt,
            model=settings.anthropic_model,
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
