"""Process-wide LLM API clients. SDK retries are disabled because callers own the retry policy."""

from functools import lru_cache

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import SecretStr

from src.shared.config import get_settings


class LLMNotConfiguredError(RuntimeError):
    def __init__(self, env_var: str) -> None:
        super().__init__(f"{env_var} not configured")


def _require_key(key: SecretStr | None, env_var: str) -> str:
    value = key.get_secret_value().strip() if key else ""
    if not value:
        raise LLMNotConfiguredError(env_var)
    return value


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    settings = get_settings()
    return AsyncAnthropic(
        api_key=_require_key(settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
        max_retries=0,
        timeout=settings.llm_timeout_seconds,
    )


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=_require_key(settings.openai_api_key, "OPENAI_API_KEY"),
        max_retries=0,
        timeout=settings.llm_timeout_seconds,
    )
