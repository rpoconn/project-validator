from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base, UTCDateTime, utcnow


class ReviewStatus(StrEnum):
    # No review is running and none has been stored (e.g. one was interrupted by a restart).
    UNREVIEWED = "unreviewed"
    PENDING = "pending"
    COMPLETE = "complete"
    ERROR = "error"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    budget_min: Mapped[int]
    budget_max: Mapped[int]
    industry: Mapped[str] = mapped_column(String(100))
    # JSON-serialised `TimelineItem`s (ISO datetimes); validated on the way in and out by schemas.
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(
            ReviewStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=ReviewStatus.PENDING,
    )
    # JSON-serialised `ProjectReview`; only set while `review_status` is `complete`.
    review: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    review_error: Mapped[str | None] = mapped_column(Text, default=None)
    review_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
