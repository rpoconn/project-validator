import pytest

from src.shared.config import Settings


def test_defaults_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    settings = Settings(_env_file=None)

    assert settings.anthropic_model == "claude-sonnet-5-5"
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert settings.anthropic_configured is False


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test", "http://b.test"]')
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "5")

    settings = Settings(_env_file=None)

    assert settings.anthropic_configured is True
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.llm_max_attempts == 5
