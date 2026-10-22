from typing import Annotated

from fastapi import APIRouter, Depends

from src.features.health.schemas import HealthResponse
from src.shared.config import Settings, get_settings

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def get_health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        anthropic_configured=settings.anthropic_configured,
        llm_mock=settings.llm_mock,
    )
