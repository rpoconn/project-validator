"""Persistence operations for projects. Other features must go through these, not the table."""

import logging
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Delete, Update, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import ProjectCreate, ProjectReview
from src.shared.database import utcnow

logger = logging.getLogger(__name__)


class ProjectNotFoundError(LookupError):
    def __init__(self, project_id: int) -> None:
        super().__init__(f"Project {project_id} not found")
        self.project_id = project_id


class ReviewAlreadyPendingError(RuntimeError):
    def __init__(self, project_id: int) -> None:
        super().__init__(f"Project {project_id} already has a review in progress")
        self.project_id = project_id


async def _execute_dml(session: AsyncSession, statement: Update | Delete) -> CursorResult[Any]:
    # DML statements return a CursorResult (with `rowcount`); the session API types it as Result.
    return cast(CursorResult[Any], await session.execute(statement))


def _column_values(data: ProjectCreate) -> dict[str, Any]:
    """The user-editable columns of a project, as stored."""
    return {
        "title": data.title,
        "description": data.description,
        "budget_min": data.budget_min,
        "budget_max": data.budget_max,
        "industry": data.industry,
        "timeline": [item.model_dump(mode="json") for item in data.timeline],
    }


async def create_project(session: AsyncSession, data: ProjectCreate) -> Project:
    project = Project(**_column_values(data), review_status=ReviewStatus.PENDING)
    session.add(project)
    await session.commit()
    logger.info("Created project %s", project.id)
    return project


async def list_projects(
    session: AsyncSession, *, limit: int | None = None, exclude_id: int | None = None
) -> Sequence[Project]:
    """Newest first, optionally capped and excluding one project (e.g. the one under review)."""
    stmt = select(Project).order_by(Project.created_at.desc(), Project.id.desc())
    if exclude_id is not None:
        stmt = stmt.where(Project.id != exclude_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.scalars(stmt)
    return result.all()


async def get_project(session: AsyncSession, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)
    return project


async def _begin_review(session: AsyncSession, project_id: int, **values: Any) -> Project:
    """Put a project into `pending`, discarding the previous outcome and applying `values`.

    The status check and update are a single conditional UPDATE, so two concurrent requests cannot
    both start a review. Raises `ReviewAlreadyPendingError` if one is already running.
    """
    result = await _execute_dml(
        session,
        update(Project)
        .where(Project.id == project_id, Project.review_status != ReviewStatus.PENDING)
        .values(
            **values,
            review_status=ReviewStatus.PENDING,
            review=None,
            review_error=None,
            review_updated_at=utcnow(),
        ),
    )
    if result.rowcount == 0:
        await session.rollback()
        await get_project(session, project_id)  # raises ProjectNotFoundError if it doesn't exist
        raise ReviewAlreadyPendingError(project_id)
    await session.commit()
    return await get_project(session, project_id)


async def mark_review_pending(session: AsyncSession, project_id: int) -> Project:
    """Start a new review, discarding the previous outcome."""
    return await _begin_review(session, project_id)


async def update_project(session: AsyncSession, project_id: int, data: ProjectCreate) -> Project:
    """Replace a project's details and start a fresh review of them.

    Rejected with `ReviewAlreadyPendingError` while a review is running, since its result would
    describe the old details.
    """
    project = await _begin_review(session, project_id, **_column_values(data))
    logger.info("Updated project %s", project_id)
    return project


async def delete_project(session: AsyncSession, project_id: int) -> None:
    result = await _execute_dml(session, delete(Project).where(Project.id == project_id))
    if result.rowcount == 0:
        await session.rollback()
        raise ProjectNotFoundError(project_id)
    await session.commit()
    logger.info("Deleted project %s", project_id)


async def reset_interrupted_reviews(session: AsyncSession) -> int:
    """Move reviews left `pending` by a previous process back to `unreviewed`.

    Background reviews die with the process, so on startup nothing can legitimately be pending.
    Returns the number of projects reset.
    """
    result = await _execute_dml(
        session,
        update(Project)
        .where(Project.review_status == ReviewStatus.PENDING)
        .values(review_status=ReviewStatus.UNREVIEWED, review_updated_at=utcnow()),
    )
    await session.commit()
    if result.rowcount:
        logger.warning("Reset %s interrupted review(s) to unreviewed", result.rowcount)
    return result.rowcount


async def set_review_result(
    session: AsyncSession, project_id: int, review: ProjectReview
) -> Project:
    project = await get_project(session, project_id)
    project.review_status = ReviewStatus.COMPLETE
    project.review = review.model_dump(mode="json")
    project.review_error = None
    project.review_updated_at = utcnow()
    await session.commit()
    logger.info("Stored review for project %s", project_id)
    return project


async def set_review_error(session: AsyncSession, project_id: int, error: str) -> Project:
    """Record a failed review. Any earlier review is discarded so only the error is shown."""
    project = await get_project(session, project_id)
    project.review_status = ReviewStatus.ERROR
    project.review = None
    project.review_error = error
    project.review_updated_at = utcnow()
    await session.commit()
    logger.warning("Review failed for project %s: %s", project_id, error)
    return project
