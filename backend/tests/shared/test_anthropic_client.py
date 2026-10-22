from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from src.shared import anthropic_client
from src.shared.anthropic_client import AnthropicNotConfiguredError, get_anthropic_client
from src.shared.config import Settings


@pytest.fixture(autouse=True)
def _fresh_client_cache() -> Iterator[None]:
    get_anthropic_client.cache_clear()
    yield
    get_anthropic_client.cache_clear()


def test_client_disables_sdk_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None, anthropic_api_key=SecretStr("sk-test"), llm_timeout_seconds=42
    )
    monkeypatch.setattr(anthropic_client, "get_settings", lambda: settings)

    client = get_anthropic_client()

    assert client.max_retries == 0
    assert client.timeout == 42
    assert get_anthropic_client() is client


@pytest.mark.parametrize("api_key", [None, SecretStr("  ")])
def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch, api_key: SecretStr | None) -> None:
    settings = Settings(_env_file=None, anthropic_api_key=api_key)
    monkeypatch.setattr(anthropic_client, "get_settings", lambda: settings)

    with pytest.raises(AnthropicNotConfiguredError, match="ANTHROPIC_API_KEY not configured"):
        get_anthropic_client()
