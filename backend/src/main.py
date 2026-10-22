"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from src.features.health.router import router as health_router
from src.features.projects import service as projects_service
from src.features.projects.router import router as projects_router
from src.shared.config import get_settings
from src.shared.database import init_db, session_factory
from src.shared.logging_config import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    # Reviews run as in-process background tasks, so any still `pending` were interrupted.
    async with session_factory() as session:
        await projects_service.reset_interrupted_reviews(session)
    settings = get_settings()
    if settings.llm_mock:
        logger.warning("LLM_MOCK is enabled; AI reviews are canned and Claude is never called")
    elif not settings.anthropic_configured:
        logger.warning("ANTHROPIC_API_KEY is not configured; AI reviews will fail")
    yield


def route_operation_id(route: APIRoute) -> str:
    """Use the handler name as the OpenAPI operationId so generated SDK names stay clean."""
    return route.name


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Project Tracker API",
        version="0.1.0",
        lifespan=lifespan,
        generate_unique_id_function=route_operation_id,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(projects_router)
    return app


app = create_app()
