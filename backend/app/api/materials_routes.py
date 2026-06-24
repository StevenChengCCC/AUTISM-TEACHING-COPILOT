from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_child_access
from app.core.database import get_db
from app.schemas.dto import (
    UploadedMaterialCreate,
    UploadedMaterialRead,
    UploadedMaterialUpdate,
)
from app.services.material_service import UploadedMaterialService

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=list[UploadedMaterialRead])
def list_materials(
    child_id: int | None = None,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    if child_id is not None:
        require_child_access(db, child_id, current, "viewer")
    return UploadedMaterialService(db).list(child_id)


@router.get("/{material_id}", response_model=UploadedMaterialRead)
def get_material(
    material_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    material = UploadedMaterialService(db).get(material_id)
    require_child_access(db, material.child_id, current, "viewer")
    return material


@router.post("", response_model=UploadedMaterialRead)
def create_uploaded_material(
    payload: UploadedMaterialCreate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_child_access(db, payload.child_id, current, "editor")
    return UploadedMaterialService(db).create(payload, current.id)


@router.patch("/{material_id}", response_model=UploadedMaterialRead)
def update_material(
    material_id: int,
    payload: UploadedMaterialUpdate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    material = UploadedMaterialService(db).get(material_id)
    require_child_access(db, material.child_id, current, "editor")
    return UploadedMaterialService(db).update(material_id, payload, current.id)


@router.delete("/{material_id}")
def delete_material(
    material_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    material = UploadedMaterialService(db).get(material_id)
    require_child_access(db, material.child_id, current, "editor")
    return UploadedMaterialService(db).delete(material_id, current.id)
