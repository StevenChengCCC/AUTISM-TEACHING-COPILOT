from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_admin
from app.core.database import get_db
from app.schemas.dto import (
    CurriculumContentCreate,
    CurriculumContentRead,
    CurriculumContentUpdate,
)
from app.services.management_service import ManagementService

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


@router.get("", response_model=list[CurriculumContentRead])
def list_curriculum(
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).list_curriculum()


@router.get("/{content_id}", response_model=CurriculumContentRead)
def get_curriculum(
    content_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).get_curriculum(content_id)


@router.post("", response_model=CurriculumContentRead)
def create_curriculum(
    payload: CurriculumContentCreate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).create_curriculum(payload, current.id)


@router.patch("/{content_id}", response_model=CurriculumContentRead)
def update_curriculum(
    content_id: int,
    payload: CurriculumContentUpdate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).update_curriculum(content_id, payload, current.id)


@router.delete("/{content_id}")
def delete_curriculum(
    content_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).delete_curriculum(content_id, current.id)
