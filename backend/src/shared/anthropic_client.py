"""Process-wide Anthropic client."""

from functools import lru_cache

from anthropic import AsyncAnthropic

from src.shared.config import get_settings


class AnthropicNotConfiguredError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("ANTHROPIC_API_KEY not configured")


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    """Shared async client. SDK retries are disabled because callers own the retry policy."""
    settings = get_settings()
    if not settings.anthropic_configured or settings.anthropic_api_key is None:
        raise AnthropicNotConfiguredError()
    return AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        max_retries=0,
        timeout=settings.llm_timeout_seconds,
    )
