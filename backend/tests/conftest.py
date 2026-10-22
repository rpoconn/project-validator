from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.features.reviews.service import get_review_runner
from src.main import create_app
from src.shared.database import create_engine, create_session_factory, get_session, init_db


class FakeReviewRunner:
    """Stands in for the background AI review; records which projects were scheduled."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    async def __call__(self, project_id: int) -> None:
        self.calls.append(project_id)


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine("sqlite+aiosqlite://")
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(db_engine)


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db_session:
        yield db_session


@pytest.fixture
def review_runner() -> FakeReviewRunner:
    return FakeReviewRunner()


@pytest.fixture
def app(
    session_factory: async_sessionmaker[AsyncSession], review_runner: FakeReviewRunner
) -> FastAPI:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db_session:
            yield db_session

    application = create_app()
    application.dependency_overrides[get_session] = override_get_session
    application.dependency_overrides[get_review_runner] = lambda: review_runner
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
