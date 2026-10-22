from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from src.features.projects.schemas import MAX_TIMELINE_ITEMS, ProjectCreate, ProjectReview
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
