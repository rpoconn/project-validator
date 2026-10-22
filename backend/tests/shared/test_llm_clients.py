from collections.abc import Callable, Iterator
from typing import Any

import pytest
from pydantic import SecretStr

from src.shared import llm_clients
from src.shared.config import Settings
from src.shared.llm_clients import (
    LLMNotConfiguredError,
    _require_key,
    get_anthropic_client,
    get_openai_client,
)

CLIENTS = [
    pytest.param(get_anthropic_client, "anthropic_api_key", "ANTHROPIC_API_KEY", id="anthropic"),
    pytest.param(get_openai_client, "openai_api_key", "OPENAI_API_KEY", id="openai"),
]


@pytest.fixture(autouse=True)
def _fresh_client_cache() -> Iterator[None]:
    get_anthropic_client.cache_clear()
    get_openai_client.cache_clear()
    yield
    get_anthropic_client.cache_clear()
    get_openai_client.cache_clear()


@pytest.mark.parametrize(("get_client", "key_field", "env_var"), CLIENTS)
def test_client_disables_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
    get_client: Callable[[], Any],
    key_field: str,
    env_var: str,
) -> None:
    settings = Settings(_env_file=None, llm_timeout_seconds=42).model_copy(
        update={key_field: SecretStr("sk-test")}
    )
    monkeypatch.setattr(llm_clients, "get_settings", lambda: settings)

    client = get_client()

    assert client.max_retries == 0
    assert client.timeout == 42
    assert get_client() is client


@pytest.mark.parametrize(("get_client", "key_field", "env_var"), CLIENTS)
@pytest.mark.parametrize("api_key", [None, SecretStr("  ")])
def test_missing_key_raises(
    monkeypatch: pytest.MonkeyPatch,
    get_client: Callable[[], Any],
    key_field: str,
    env_var: str,
    api_key: SecretStr | None,
) -> None:
    settings = Settings(_env_file=None).model_copy(update={key_field: api_key})
    monkeypatch.setattr(llm_clients, "get_settings", lambda: settings)

    with pytest.raises(LLMNotConfiguredError, match=f"{env_var} not configured"):
        get_client()


def test_require_key_strips_surrounding_whitespace() -> None:
    assert _require_key(SecretStr("  sk-test \n"), "ANY_KEY") == "sk-test"

    with pytest.raises(LLMNotConfiguredError, match="ANY_KEY not configured"):
        _require_key(SecretStr("   "), "ANY_KEY")
