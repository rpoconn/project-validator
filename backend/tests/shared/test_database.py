from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Integer, inspect
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import (
    Base,
    UTCDateTime,
    create_engine,
    create_session_factory,
    init_db,
)


class _Widget(Base):
    __tablename__ = "_test_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


async def test_init_db_creates_parent_dir_and_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "app.db"
    engine = create_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        await init_db(engine)

        assert db_path.exists()
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        assert "_test_widgets" in tables
    finally:
        await engine.dispose()


class _Event(Base):
    __tablename__ = "_test_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime)


async def test_in_memory_engine_shares_one_database_across_sessions() -> None:
    engine = create_engine("sqlite+aiosqlite://")
    try:
        await init_db(engine)
        factory = create_session_factory(engine)
        eastern = timezone(timedelta(hours=-5))
        async with factory() as writer:
            writer.add(_Event(id=1, at=datetime(2027, 1, 1, 12, tzinfo=eastern)))
            await writer.commit()

        async with factory() as reader:
            event = await reader.get(_Event, 1)

        assert event is not None
        assert event.at == datetime(2027, 1, 1, 17, tzinfo=UTC)
        assert event.at.tzinfo == UTC
    finally:
        await engine.dispose()


async def test_utc_datetime_rejects_naive_values() -> None:
    engine = create_engine("sqlite+aiosqlite://")
    try:
        await init_db(engine)
        async with create_session_factory(engine)() as session:
            session.add(_Event(id=1, at=datetime(2027, 1, 1)))
            with pytest.raises(StatementError, match="timezone-aware"):
                await session.commit()
    finally:
        await engine.dispose()
