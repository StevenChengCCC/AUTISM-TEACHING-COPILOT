from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dto import UploadedMaterialCreate, UploadedMaterialRead
from app.services.material_service import UploadedMaterialService

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("/children/{child_id}", response_model=list[UploadedMaterialRead])
def list_child_materials(child_id: int, db: Session = Depends(get_db)):
    return UploadedMaterialService(db).list_for_child(child_id)


@router.post("", response_model=UploadedMaterialRead)
def create_uploaded_material(
    payload: UploadedMaterialCreate, db: Session = Depends(get_db)
):
    return UploadedMaterialService(db).create(payload)
