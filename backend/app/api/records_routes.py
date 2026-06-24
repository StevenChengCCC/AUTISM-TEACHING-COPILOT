from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dto import SessionRecordCreate, SessionRecordRead
from app.services.lesson_service import LessonService

router = APIRouter(prefix="/records", tags=["records"])


@router.post("", response_model=SessionRecordRead)
def create_session_record(payload: SessionRecordCreate, db: Session = Depends(get_db)):
    return LessonService(db).create_record(payload)
