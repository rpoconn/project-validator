from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.projects import service
from src.features.projects.schemas import ProjectReview
from tests.conftest import FakeReviewRunner
from tests.features.projects.factories import project_payload


async def _create(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/api/projects", json=project_payload(**overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_create_project_returns_pending_and_schedules_review(
    client: AsyncClient, review_runner: FakeReviewRunner
) -> None:
    body = await _create(client)

    assert body["id"] > 0
    assert body["title"] == "Warehouse automation"
    assert body["review_status"] == "pending"
    assert body["review"] is None
    assert body["timeline"][0] == {"goal": "Vendor selected", "due_at": "2027-01-15T00:00:00Z"}
    assert body["created_at"].endswith("Z")
    assert review_runner.calls == [body["id"]]


async def test_create_project_validation_error_shape(
    client: AsyncClient, review_runner: FakeReviewRunner
) -> None:
    response = await client.post(
        "/api/projects", json=project_payload(title="", budget_min=10, budget_max=5)
    )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert ["body", "title"] in [error["loc"] for error in errors]
    assert review_runner.calls == []


async def test_create_project_rejects_inverted_budget(client: AsyncClient) -> None:
    response = await client.post("/api/projects", json=project_payload(budget_min=10, budget_max=5))

    assert response.status_code == 422
    assert "budget_max must be greater than or equal" in response.text


async def test_list_projects_newest_first(client: AsyncClient) -> None:
    assert (await client.get("/api/projects")).json() == []

    first = await _create(client, title="First")
    second = await _create(client, title="Second")

    response = await client.get("/api/projects")

    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [second["id"], first["id"]]


async def test_get_project(client: AsyncClient) -> None:
    created = await _create(client)

    response = await client.get(f"/api/projects/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


async def test_get_project_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/projects/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project 999 not found"}


async def test_rerun_review_resets_to_pending(
    client: AsyncClient, session: AsyncSession, review_runner: FakeReviewRunner
) -> None:
    created = await _create(client)
    await service.set_review_error(session, created["id"], "APIConnectionError: timed out")

    response = await client.post(f"/api/projects/{created['id']}/review")

    assert response.status_code == 202
    body = response.json()
    assert body["review_status"] == "pending"
    assert body["review_error"] is None
    assert review_runner.calls == [created["id"], created["id"]]


async def test_rerun_review_conflicts_while_pending(
    client: AsyncClient, review_runner: FakeReviewRunner
) -> None:
    created = await _create(client)  # the creation review is still pending

    response = await client.post(f"/api/projects/{created['id']}/review")

    assert response.status_code == 409
    assert response.json() == {
        "detail": f"Project {created['id']} already has a review in progress"
    }
    assert review_runner.calls == [created["id"]]


async def test_rerun_review_recovers_interrupted_review(
    client: AsyncClient, session: AsyncSession, review_runner: FakeReviewRunner
) -> None:
    created = await _create(client)
    await service.reset_interrupted_reviews(session)  # what startup does after a restart
    assert (await client.get(f"/api/projects/{created['id']}")).json()["review_status"] == (
        "unreviewed"
    )

    response = await client.post(f"/api/projects/{created['id']}/review")

    assert response.status_code == 202
    assert response.json()["review_status"] == "pending"
    assert review_runner.calls == [created["id"], created["id"]]


async def test_review_result_is_served(client: AsyncClient, session: AsyncSession) -> None:
    created = await _create(client)
    review = ProjectReview(summary="Solid plan.", tags=["a", "b", "c"], risks=["Scope creep"])
    await service.set_review_result(session, created["id"], review)

    body = (await client.get(f"/api/projects/{created['id']}")).json()

    assert body["review_status"] == "complete"
    assert body["review"] == review.model_dump()
    assert body["review_updated_at"] is not None


async def test_rerun_review_not_found(client: AsyncClient, review_runner: FakeReviewRunner) -> None:
    response = await client.post("/api/projects/999/review")

    assert response.status_code == 404
    assert review_runner.calls == []


async def test_openapi_exposes_project_schemas_and_operation_ids(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()

    schemas = spec["components"]["schemas"]
    for name in ("ProjectCreate", "ProjectRead", "ProjectReview", "TimelineItem", "ReviewStatus"):
        assert name in schemas
    paths = spec["paths"]
    assert paths["/api/projects"]["get"]["operationId"] == "list_projects"
    assert paths["/api/projects"]["post"]["operationId"] == "create_project"
    assert paths["/api/projects/{project_id}"]["get"]["operationId"] == "get_project"
    rerun = paths["/api/projects/{project_id}/review"]["post"]
    assert rerun["operationId"] == "rerun_review"
    assert {"202", "404", "409"} <= set(rerun["responses"])
    assert schemas["ReviewStatus"]["enum"] == ["unreviewed", "pending", "complete", "error"]
