from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.projects import service
from src.features.projects.models import Project
from src.features.projects.schemas import ProjectCreate, ProjectRead
from src.features.reviews.service import ReviewRunner, get_review_runner
from src.shared.database import get_session

router = APIRouter(prefix="/api/projects", tags=["projects"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ReviewRunnerDep = Annotated[ReviewRunner, Depends(get_review_runner)]

NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Project not found"}
}
RERUN_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    status.HTTP_409_CONFLICT: {"description": "A review is already in progress"},
}


async def _get_or_404(session: AsyncSession, project_id: int) -> Project:
    try:
        return await service.get_project(session, project_id)
    except service.ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("")
async def list_projects(session: SessionDep) -> list[ProjectRead]:
    projects = await service.list_projects(session)
    return [ProjectRead.model_validate(project) for project in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    run_review: ReviewRunnerDep,
) -> ProjectRead:
    project = await service.create_project(session, payload)
    background_tasks.add_task(run_review, project.id)
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", responses=NOT_FOUND_RESPONSE)
async def get_project(project_id: int, session: SessionDep) -> ProjectRead:
    return ProjectRead.model_validate(await _get_or_404(session, project_id))


@router.post(
    "/{project_id}/review", status_code=status.HTTP_202_ACCEPTED, responses=RERUN_RESPONSES
)
async def rerun_review(
    project_id: int,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    run_review: ReviewRunnerDep,
) -> ProjectRead:
    """Start a fresh review. Rejected with 409 while one is already pending."""
    try:
        project = await service.mark_review_pending(session, project_id)
    except service.ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.ReviewAlreadyPendingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background_tasks.add_task(run_review, project.id)
    return ProjectRead.model_validate(project)
