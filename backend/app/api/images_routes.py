from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dto import (
    ConfirmImageRequest,
    ImageCandidate,
    ImageNeedRequest,
    ImagePipelineResult,
)
from app.services.image_asset_service import ImageAssetService
from app.services.image_pipeline_service import ImagePipelineService

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/pipeline", response_model=ImagePipelineResult)
def run_image_pipeline(payload: ImageNeedRequest, db: Session = Depends(get_db)):
    return ImagePipelineService(db).run(payload)


@router.post("/confirm", response_model=list[ImageCandidate])
def confirm_images(payload: ConfirmImageRequest, db: Session = Depends(get_db)):
    return ImageAssetService(db).confirm_assets(payload)


@router.get("/assets", response_model=list[ImageCandidate])
def list_image_assets(db: Session = Depends(get_db)):
    return ImagePipelineService(db).list_assets()
