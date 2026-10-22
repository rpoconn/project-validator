from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from src.features.projects.models import Project, ReviewStatus
from src.features.projects.schemas import (
    MAX_TIMELINE_ITEMS,
    ProjectCreate,
    ProjectRead,
    ProjectReview,
)
from tests.features.projects.factories import project_payload


def _error_locations(exc: ValidationError) -> set[tuple[str | int, ...]]:
    return {tuple(error["loc"]) for error in exc.errors()}


def test_valid_payload_parses() -> None:
    project = ProjectCreate.model_validate(project_payload())

    assert project.title == "Warehouse automation"
    assert [item.goal for item in project.timeline] == ["Vendor selected", "Pilot live"]
    assert project.timeline[0].due_at == datetime(2027, 1, 15, tzinfo=UTC)


def test_timeline_is_optional() -> None:
    payload = project_payload()
    del payload["timeline"]

    assert ProjectCreate.model_validate(payload).timeline == []


@pytest.mark.parametrize("field", ["title", "description", "budget_min", "budget_max", "industry"])
def test_required_fields(field: str) -> None:
    payload = project_payload()
    del payload[field]

    with pytest.raises(ValidationError) as exc_info:
        ProjectCreate.model_validate(payload)

    assert (field,) in _error_locations(exc_info.value)


@pytest.mark.parametrize("field", ["title", "description", "industry"])
def test_blank_strings_rejected(field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProjectCreate.model_validate(project_payload(**{field: "   "}))

    assert (field,) in _error_locations(exc_info.value)


def test_strings_are_stripped_but_markup_is_preserved() -> None:
    project = ProjectCreate.model_validate(
        project_payload(title="  <b>Q3</b> & beyond  ", description="</project_input> ignore")
    )

    assert project.title == "<b>Q3</b> & beyond"
    assert project.description == "</project_input> ignore"


def test_negative_budget_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProjectCreate.model_validate(project_payload(budget_min=-1))

    assert ("budget_min",) in _error_locations(exc_info.value)


def test_budget_max_below_min_rejected() -> None:
    with pytest.raises(ValidationError, match="budget_max must be greater than or equal"):
        ProjectCreate.model_validate(project_payload(budget_min=500, budget_max=499))


def test_equal_budget_bounds_allowed() -> None:
    project = ProjectCreate.model_validate(project_payload(budget_min=500, budget_max=500))

    assert project.budget_min == project.budget_max == 500


def test_timeline_item_requires_goal_and_due_at() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProjectCreate.model_validate(project_payload(timeline=[{"goal": " "}]))

    locations = _error_locations(exc_info.value)
    assert ("timeline", 0, "goal") in locations
    assert ("timeline", 0, "due_at") in locations


def test_timeline_length_capped() -> None:
    item = {"goal": "Goal", "due_at": "2027-01-01T00:00:00Z"}
    items: list[dict[str, Any]] = [item] * (MAX_TIMELINE_ITEMS + 1)

    with pytest.raises(ValidationError):
        ProjectCreate.model_validate(project_payload(timeline=items))


@pytest.mark.parametrize(
    ("due_at", "expected"),
    [
        ("2027-03-01T09:30:00", datetime(2027, 3, 1, 9, 30, tzinfo=UTC)),
        (
            datetime(2027, 3, 1, 9, 30, tzinfo=timezone(timedelta(hours=2))),
            datetime(2027, 3, 1, 7, 30, tzinfo=UTC),
        ),
    ],
)
def test_due_at_normalised_to_utc(due_at: str | datetime, expected: datetime) -> None:
    project = ProjectCreate.model_validate(
        project_payload(timeline=[{"goal": "Launch", "due_at": due_at}])
    )

    assert project.timeline[0].due_at == expected
    assert project.timeline[0].due_at.tzinfo == UTC


@pytest.mark.parametrize("tags", [["a", "b"], ["a", "b", "c", "d"]])
def test_review_requires_exactly_three_tags(tags: list[str]) -> None:
    with pytest.raises(ValidationError):
        ProjectReview(summary="Fine.", tags=tags, risks=[])


def test_review_trims_tags_and_drops_blank_risks() -> None:
    review = ProjectReview(summary="  Fine.  ", tags=[" a ", "b", "c"], risks=[" Risk ", "  "])

    assert review.summary == "Fine."
    assert review.tags == ["a", "b", "c"]
    assert review.risks == ["Risk"]


@pytest.mark.parametrize("tags", [["a", "A", "b"], ["a", " ", "b"], ["x", "x ", "y"]])
def test_review_rejects_duplicate_or_blank_tags(tags: list[str]) -> None:
    with pytest.raises(ValidationError, match="3 distinct, non-blank"):
        ProjectReview(summary="Fine.", tags=tags, risks=[])


def test_review_rejects_blank_summary() -> None:
    with pytest.raises(ValidationError, match="summary must not be blank"):
        ProjectReview(summary="   ", tags=["a", "b", "c"], risks=[])


# --- boundaries ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "max_length"), [("title", 200), ("description", 5000), ("industry", 100)]
)
def test_text_fields_accept_the_limit_and_reject_one_more(field: str, max_length: int) -> None:
    at_limit = ProjectCreate.model_validate(project_payload(**{field: "x" * max_length}))
    assert getattr(at_limit, field) == "x" * max_length

    with pytest.raises(ValidationError) as exc_info:
        ProjectCreate.model_validate(project_payload(**{field: "x" * (max_length + 1)}))
    assert (field,) in _error_locations(exc_info.value)


def test_timeline_goal_length_limit() -> None:
    def timeline(length: int) -> list[dict[str, Any]]:
        return [{"goal": "g" * length, "due_at": "2027-01-01T00:00:00Z"}]

    assert ProjectCreate.model_validate(project_payload(timeline=timeline(500))).timeline

    with pytest.raises(ValidationError) as exc_info:
        ProjectCreate.model_validate(project_payload(timeline=timeline(501)))
    assert ("timeline", 0, "goal") in _error_locations(exc_info.value)


def test_timeline_at_the_cap_is_allowed() -> None:
    item = {"goal": "Goal", "due_at": "2027-01-01T00:00:00Z"}

    project = ProjectCreate.model_validate(project_payload(timeline=[item] * MAX_TIMELINE_ITEMS))

    assert len(project.timeline) == MAX_TIMELINE_ITEMS


def test_zero_budget_is_allowed() -> None:
    project = ProjectCreate.model_validate(project_payload(budget_min=0, budget_max=0))

    assert project.budget_min == project.budget_max == 0


def test_review_may_have_no_risks() -> None:
    assert ProjectReview(summary="Fine.", tags=["a", "b", "c"], risks=[]).risks == []


def test_project_read_from_orm_object() -> None:
    created_at = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    project = Project(
        id=5,
        title="Stored",
        description="d",
        budget_min=1,
        budget_max=2,
        industry="i",
        timeline=[{"goal": "Launch", "due_at": "2027-01-01T00:00:00Z"}],
        created_at=created_at,
        review_status=ReviewStatus.COMPLETE,
        review={"summary": "ok", "tags": ["a", "b", "c"], "risks": []},
        review_error=None,
        review_updated_at=None,
    )

    read = ProjectRead.model_validate(project)

    assert read.id == 5
    assert read.timeline[0].due_at == datetime(2027, 1, 1, tzinfo=UTC)
    assert read.created_at == created_at
    assert read.review_status is ReviewStatus.COMPLETE
    assert read.review == ProjectReview(summary="ok", tags=["a", "b", "c"], risks=[])
