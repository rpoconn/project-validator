from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.features.projects import service
from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import ProjectCreate, ProjectRead, ProjectReview
from tests.features.projects.factories import project_payload

REVIEW = ProjectReview(
    summary="Ambitious automation rollout. Budget looks tight.",
    tags=["automation", "logistics", "capex"],
    risks=["Vendor lock-in", "Pilot timeline is aggressive"],
)


async def _create(session: AsyncSession, **overrides: object) -> Project:
    return await service.create_project(
        session, ProjectCreate.model_validate(project_payload(**overrides))
    )


async def test_create_project_persists_pending_project(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    created = await _create(session)

    # Read back through a fresh session to prove it was committed and round-trips cleanly.
    async with session_factory() as other:
        loaded = ProjectRead.model_validate(await service.get_project(other, created.id))

    assert loaded.title == "Warehouse automation"
    assert loaded.review_status is ReviewStatus.PENDING
    assert loaded.review is None
    assert loaded.review_error is None
    assert loaded.created_at.tzinfo == UTC
    assert loaded.timeline[1].goal == "Pilot live"
    assert loaded.timeline[1].due_at == datetime(2027, 6, 1, 12, tzinfo=UTC)


async def test_list_projects_newest_first(session: AsyncSession) -> None:
    first = await _create(session, title="First")
    second = await _create(session, title="Second")
    third = await _create(session, title="Third")

    projects = await service.list_projects(session)

    assert [p.id for p in projects] == [third.id, second.id, first.id]


async def test_list_projects_limit_and_exclude(session: AsyncSession) -> None:
    first = await _create(session, title="First")
    second = await _create(session, title="Second")
    third = await _create(session, title="Third")

    projects = await service.list_projects(session, limit=1, exclude_id=third.id)
    assert [p.id for p in projects] == [second.id]

    projects = await service.list_projects(session, exclude_id=second.id)
    assert [p.id for p in projects] == [third.id, first.id]


async def test_list_projects_empty(session: AsyncSession) -> None:
    assert await service.list_projects(session) == []


async def test_get_project_missing_raises(session: AsyncSession) -> None:
    with pytest.raises(service.ProjectNotFoundError, match="Project 999 not found"):
        await service.get_project(session, 999)


async def test_set_review_result(session: AsyncSession) -> None:
    project = await _create(session)

    updated = await service.set_review_result(session, project.id, REVIEW)

    read = ProjectRead.model_validate(updated)
    assert read.review_status is ReviewStatus.COMPLETE
    assert read.review == REVIEW
    assert read.review_error is None
    assert read.review_updated_at is not None


async def test_set_review_error_discards_previous_review(session: AsyncSession) -> None:
    project = await _create(session)
    await service.set_review_result(session, project.id, REVIEW)

    updated = await service.set_review_error(session, project.id, "RateLimitError: slow down")

    assert updated.review_status is ReviewStatus.ERROR
    assert updated.review_error == "RateLimitError: slow down"
    assert updated.review is None


@pytest.mark.parametrize("previous", ["error", "complete", "unreviewed"])
async def test_mark_review_pending_clears_previous_outcome(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], previous: str
) -> None:
    project = await _create(session)
    if previous == "error":
        await service.set_review_error(session, project.id, "boom")
    elif previous == "complete":
        await service.set_review_result(session, project.id, REVIEW)
    else:
        await service.reset_interrupted_reviews(session)

    updated = await service.mark_review_pending(session, project.id)

    assert updated.review_status is ReviewStatus.PENDING
    assert updated.review is None
    assert updated.review_error is None
    async with session_factory() as other:
        stored = await service.get_project(other, project.id)
    assert stored.review_status is ReviewStatus.PENDING
    assert stored.review is None


async def test_mark_review_pending_rejects_review_in_progress(session: AsyncSession) -> None:
    project = await _create(session)  # new projects start pending

    with pytest.raises(service.ReviewAlreadyPendingError, match="already has a review in progress"):
        await service.mark_review_pending(session, project.id)


async def test_update_project_replaces_details_and_restarts_review(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    project = await _create(session)
    await service.set_review_result(session, project.id, REVIEW)
    data = ProjectCreate.model_validate(
        project_payload(title="Renamed", industry="Retail", timeline=[])
    )

    updated = await service.update_project(session, project.id, data)

    assert updated.id == project.id
    assert updated.title == "Renamed"
    assert updated.industry == "Retail"
    assert updated.timeline == []
    assert updated.review_status is ReviewStatus.PENDING
    assert updated.review is None
    async with session_factory() as other:
        stored = await service.get_project(other, project.id)
    assert stored.title == "Renamed"
    assert stored.review_status is ReviewStatus.PENDING


async def test_update_project_rejects_review_in_progress(session: AsyncSession) -> None:
    project = await _create(session)  # new projects start pending
    data = ProjectCreate.model_validate(project_payload(title="Renamed"))

    with pytest.raises(service.ReviewAlreadyPendingError):
        await service.update_project(session, project.id, data)

    await session.refresh(project)
    assert project.title == "Warehouse automation"


async def test_delete_project_removes_it(session: AsyncSession) -> None:
    project = await _create(session)
    kept = await _create(session, title="Kept")

    await service.delete_project(session, project.id)

    assert [p.id for p in await service.list_projects(session)] == [kept.id]
    with pytest.raises(service.ProjectNotFoundError):
        await service.get_project(session, project.id)


async def test_reset_interrupted_reviews_only_touches_pending(session: AsyncSession) -> None:
    pending = await _create(session, title="Pending")
    complete = await _create(session, title="Complete")
    await service.set_review_result(session, complete.id, REVIEW)
    failed = await _create(session, title="Failed")
    await service.set_review_error(session, failed.id, "boom")

    assert await service.reset_interrupted_reviews(session) == 1

    for project in (pending, complete, failed):
        await session.refresh(project)
    assert pending.review_status is ReviewStatus.UNREVIEWED
    assert complete.review_status is ReviewStatus.COMPLETE
    assert complete.review == REVIEW.model_dump(mode="json")
    assert failed.review_status is ReviewStatus.ERROR
    assert await service.reset_interrupted_reviews(session) == 0


@pytest.mark.parametrize(
    "operation",
    [
        lambda s: service.mark_review_pending(s, 42),
        lambda s: service.set_review_result(s, 42, REVIEW),
        lambda s: service.set_review_error(s, 42, "boom"),
        lambda s: service.update_project(s, 42, ProjectCreate.model_validate(project_payload())),
        lambda s: service.delete_project(s, 42),
    ],
)
async def test_updates_on_missing_project_raise(
    session: AsyncSession, operation: Callable[[AsyncSession], Awaitable[Project | None]]
) -> None:
    with pytest.raises(service.ProjectNotFoundError):
        await operation(session)


# --- helpers and timestamps ---------------------------------------------------------------------


def test_column_values_serialises_timeline_for_json_storage() -> None:
    data = ProjectCreate.model_validate(
        project_payload(timeline=[{"goal": " Launch ", "due_at": "2027-01-01T09:00:00+02:00"}])
    )

    values = service._column_values(data)

    assert set(values) == {
        "title",
        "description",
        "budget_min",
        "budget_max",
        "industry",
        "timeline",
    }
    assert values["timeline"] == [{"goal": "Launch", "due_at": "2027-01-01T07:00:00Z"}]


async def test_reset_interrupted_reviews_stamps_review_updated_at(session: AsyncSession) -> None:
    project = await _create(session)
    assert project.review_updated_at is None

    await service.reset_interrupted_reviews(session)

    await session.refresh(project)
    assert project.review_updated_at is not None
    assert project.review_updated_at.tzinfo == UTC
