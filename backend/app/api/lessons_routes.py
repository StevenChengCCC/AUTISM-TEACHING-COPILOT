from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dto import LessonPlanRequest, LessonPlanResponse
from app.services.lesson_service import LessonService

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.post("", response_model=LessonPlanResponse)
def create_lesson(payload: LessonPlanRequest, db: Session = Depends(get_db)):
    return LessonService(db).create_lesson(payload)
