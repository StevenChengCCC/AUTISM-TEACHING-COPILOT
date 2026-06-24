from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dto import (
    ChildProfileCreate,
    ChildProfileRead,
    ConfirmImageRequest,
    ImageCandidate,
    ImageNeedRequest,
    ImagePipelineResult,
    LessonPlanRequest,
    LessonPlanResponse,
    SessionRecordCreate,
    SessionRecordRead,
)
from app.services.profile_service import ChildProfileService
from app.services.image_pipeline_service import ImagePipelineService
from app.services.image_asset_service import ImageAssetService
from app.services.lesson_service import LessonService

router = APIRouter()

@router.post("/children", response_model=ChildProfileRead)
def create_child_profile(payload: ChildProfileCreate, db: Session = Depends(get_db)):
    return ChildProfileService(db).create_child_profile(payload)

@router.get("/children", response_model=list[ChildProfileRead])
def list_child_profiles(db: Session = Depends(get_db)):
    return ChildProfileService(db).list_child_profiles()

@router.post("/images/pipeline", response_model=ImagePipelineResult)
def run_image_pipeline(payload: ImageNeedRequest, db: Session = Depends(get_db)):
    return ImagePipelineService(db).run(payload)

@router.post("/images/confirm", response_model=list[ImageCandidate])
def confirm_images(payload: ConfirmImageRequest, db: Session = Depends(get_db)):
    return ImageAssetService(db).confirm_assets(payload)

@router.get("/images/assets", response_model=list[ImageCandidate])
def list_image_assets(db: Session = Depends(get_db)):
    return ImagePipelineService(db).list_assets()

@router.post("/lessons", response_model=LessonPlanResponse)
def create_lesson(payload: LessonPlanRequest, db: Session = Depends(get_db)):
    return LessonService(db).create_lesson(payload)

@router.post("/records", response_model=SessionRecordRead)
def create_session_record(payload: SessionRecordCreate, db: Session = Depends(get_db)):
    return LessonService(db).create_record(payload)
