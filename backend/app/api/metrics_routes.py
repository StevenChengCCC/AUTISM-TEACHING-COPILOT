from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentTeacher,
    get_current_teacher,
    load_teacher,
    require_child_access,
)
from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.schemas.dto import DirectUseMetrics
from app.services.feedback_service import LessonFeedbackService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/direct-use", response_model=DirectUseMetrics)
def direct_use_metrics(
    child_id: int | None = Query(default=None),
    goal_id: int | None = Query(default=None),
    since: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    if child_id is not None:
        require_child_access(db, child_id, current, "viewer")
    else:
        # Aggregate across children is an admin-level read.
        load_teacher(db, current)

    parsed_since: datetime | None = None
    if since:
        try:
            parsed_since = datetime.fromisoformat(since)
        except ValueError as exc:
            raise ValidationError(
                "since must be an ISO-8601 datetime."
            ) from exc

    return LessonFeedbackService(db).direct_use_metrics(
        child_id=child_id, goal_id=goal_id, since=parsed_since
    )
