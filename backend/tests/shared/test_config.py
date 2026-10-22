import pytest
from pydantic import SecretStr

from src.shared.config import LLMProvider, Settings


def test_defaults_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = Settings(_env_file=None)

    assert settings.anthropic_model == "claude-sonnet-5-5"
    assert settings.openai_model == "gpt-5.5"
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert settings.anthropic_configured is False
    assert settings.openai_configured is False
    assert settings.active_llm_provider == "anthropic"
    assert settings.llm_configured is False


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test", "http://b.test"]')
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "5")

    settings = Settings(_env_file=None)

    assert settings.anthropic_configured is True
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.llm_max_attempts == 5


ANTHROPIC_KEY = SecretStr("sk-ant")
OPENAI_KEY = SecretStr("sk-openai")


@pytest.mark.parametrize(
    ("llm_provider", "anthropic_key", "openai_key", "provider", "configured"),
    [
        # Unset provider: whichever key is configured, Anthropic when both or neither are.
        (None, ANTHROPIC_KEY, None, "anthropic", True),
        (None, None, OPENAI_KEY, "openai", True),
        (None, ANTHROPIC_KEY, OPENAI_KEY, "anthropic", True),
        (None, SecretStr(" "), OPENAI_KEY, "openai", True),
        (None, None, None, "anthropic", False),
        # An explicit provider wins, even when only the other key is set.
        ("openai", ANTHROPIC_KEY, OPENAI_KEY, "openai", True),
        ("openai", ANTHROPIC_KEY, None, "openai", False),
        ("anthropic", None, OPENAI_KEY, "anthropic", False),
    ],
)
def test_active_llm_provider(
    llm_provider: LLMProvider | None,
    anthropic_key: SecretStr | None,
    openai_key: SecretStr | None,
    provider: LLMProvider,
    configured: bool,
) -> None:
    settings = Settings(
        _env_file=None,
        llm_provider=llm_provider,
        anthropic_api_key=anthropic_key,
        openai_api_key=openai_key,
    )

    assert settings.active_llm_provider == provider
    assert settings.llm_configured is configured


def test_reads_provider_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    settings = Settings(_env_file=None)

    assert settings.active_llm_provider == "openai"
    assert settings.llm_configured is True
    assert settings.openai_model == "gpt-test"
