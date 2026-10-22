import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr

from src.shared.config import Settings, get_settings


@pytest.mark.parametrize(
    ("api_key", "expected"),
    [(SecretStr("sk-test"), True), (None, False), (SecretStr("   "), False)],
)
async def test_health_reports_api_key_configuration(
    app: FastAPI, client: AsyncClient, api_key: SecretStr | None, expected: bool
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, anthropic_api_key=api_key
    )

    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "llm_provider": "anthropic",
        "llm_configured": expected,
        "llm_mock": False,
    }


async def test_health_reports_openai_provider(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, llm_provider="openai", openai_api_key=SecretStr("sk-test")
    )

    response = await client.get("/api/health")

    assert response.json() == {
        "status": "ok",
        "llm_provider": "openai",
        "llm_configured": True,
        "llm_mock": False,
    }


async def test_health_reports_mock_reviews(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, llm_mock=True)

    response = await client.get("/api/health")

    assert response.json() == {
        "status": "ok",
        "llm_provider": "anthropic",
        "llm_configured": False,
        "llm_mock": True,
    }


async def test_openapi_spec_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert spec["paths"]["/api/health"]["get"]["operationId"] == "get_health"
    assert "HealthResponse" in spec["components"]["schemas"]
