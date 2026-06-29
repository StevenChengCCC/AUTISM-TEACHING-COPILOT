from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_child_access
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.domain.models import LessonPackage
from app.schemas.dto import (
    ArtifactFeedbackRead,
    ArtifactFeedbackSubmit,
    LessonPlanRequest,
    LessonPlanResponse,
)
from app.services.feedback_service import LessonFeedbackService
from app.services.lesson_service import LessonService

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.post("", response_model=LessonPlanResponse)
def create_lesson(
    payload: LessonPlanRequest,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_child_access(db, payload.child_id, current, "editor")
    return LessonService(db).create_lesson(payload, current.id)


def _lesson_child_id(db: Session, lesson_id: int) -> int:
    lesson = db.query(LessonPackage).filter(LessonPackage.id == lesson_id).first()
    if not lesson:
        raise NotFoundError("Lesson package not found")
    return lesson.child_id


@router.post("/{lesson_id}/feedback", response_model=list[ArtifactFeedbackRead])
def submit_lesson_feedback(
    lesson_id: int,
    payload: ArtifactFeedbackSubmit,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_child_access(db, _lesson_child_id(db, lesson_id), current, "editor")
    return LessonFeedbackService(db).submit_feedback(lesson_id, payload, current.id)


@router.get("/{lesson_id}/feedback", response_model=list[ArtifactFeedbackRead])
def list_lesson_feedback(
    lesson_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_child_access(db, _lesson_child_id(db, lesson_id), current, "viewer")
    return LessonFeedbackService(db).list_feedback(lesson_id)
