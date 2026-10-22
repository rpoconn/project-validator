"""Async SQLAlchemy engine, session factory and declarative base."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Dialect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from src.shared.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetime column.

    SQLite drops tzinfo on storage, so values are normalised to UTC on write and re-tagged as UTC
    on read. Naive datetimes are rejected rather than silently assumed to be UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_sqlite_memory(database_url: str) -> bool:
    url = make_url(database_url)
    return url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:")


def create_engine(database_url: str) -> AsyncEngine:
    if _is_sqlite_memory(database_url):
        # Every pooled connection to `:memory:` would be a separate empty database; share one.
        return create_async_engine(database_url, poolclass=StaticPool)
    return create_async_engine(database_url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


engine = create_engine(get_settings().database_url)
session_factory = create_session_factory(engine)


def _ensure_sqlite_dir(database_url: str) -> None:
    if _is_sqlite_memory(database_url):
        return
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database:
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)


async def init_db(db_engine: AsyncEngine = engine) -> None:
    """Create all tables registered on `Base.metadata`."""
    _ensure_sqlite_dir(str(db_engine.url))
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialised at %s", db_engine.url.render_as_string(hide_password=True))


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with session_factory() as session:
        yield session
