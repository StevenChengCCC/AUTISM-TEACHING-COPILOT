from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_child_access
from app.core.database import get_db
from app.schemas.dto import LessonPlanRequest, LessonPlanResponse
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
