from datetime import UTC, datetime
from functools import partial
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.features.projects.models import ReviewStatus

# Tag-breaking characters (`<`, `>`, `&`) are deliberately kept: escaping happens when the review
# prompt is built, so the stored data stays exactly what the user typed.
_non_blank = partial(StringConstraints, strip_whitespace=True, min_length=1)
Title = Annotated[str, _non_blank(max_length=200)]
Description = Annotated[str, _non_blank(max_length=5000)]
Industry = Annotated[str, _non_blank(max_length=100)]
Goal = Annotated[str, _non_blank(max_length=500)]
Budget = Annotated[int, Field(ge=0)]

MAX_TIMELINE_ITEMS = 50


class TimelineItem(BaseModel):
    goal: Goal
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def _normalise_to_utc(cls, value: datetime) -> datetime:
        """Treat naive datetimes as UTC so everything stored and returned is timezone-aware."""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ProjectCreate(BaseModel):
    title: Title
    description: Description
    budget_min: Budget
    budget_max: Budget
    industry: Industry
    timeline: list[TimelineItem] = Field(default_factory=list, max_length=MAX_TIMELINE_ITEMS)

    @model_validator(mode="after")
    def _check_budget_range(self) -> Self:
        if self.budget_max < self.budget_min:
            raise ValueError("budget_max must be greater than or equal to budget_min")
        return self


class ProjectReview(BaseModel):
    """AI risk review of a project; also the structured-output schema requested from Claude."""

    summary: str = Field(description="A 2-3 sentence summary of the project and its risk profile.")
    tags: list[str] = Field(
        min_length=3,
        max_length=3,
        description="Exactly three short (1-3 word) tags categorising the project.",
    )
    risks: list[str] = Field(
        description="Risk checklist: one concise, specific risk per item.",
    )

    @field_validator("summary")
    @classmethod
    def _summary_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("summary must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def _three_distinct_tags(cls, value: list[str]) -> list[str]:
        """Trim and de-duplicate (case-insensitively); fewer than 3 left is a malformed review."""
        tags: list[str] = []
        for tag in (raw.strip() for raw in value):
            if tag and tag.casefold() not in {seen.casefold() for seen in tags}:
                tags.append(tag)
        if len(tags) != 3:
            raise ValueError("tags must contain 3 distinct, non-blank values")
        return tags

    @field_validator("risks")
    @classmethod
    def _drop_blank_risks(cls, value: list[str]) -> list[str]:
        return [risk.strip() for risk in value if risk.strip()]


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    budget_min: int
    budget_max: int
    industry: str
    timeline: list[TimelineItem]
    created_at: datetime
    review_status: ReviewStatus
    review: ProjectReview | None
    review_error: str | None
    review_updated_at: datetime | None
