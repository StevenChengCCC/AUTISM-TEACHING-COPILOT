from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_admin
from app.core.database import get_db
from app.schemas.dto import (
    TeacherChildAccessCreate,
    TeacherChildAccessRead,
    TeacherChildAccessUpdate,
)
from app.services.management_service import ManagementService

router = APIRouter(prefix="/access", tags=["access"])


@router.get("", response_model=list[TeacherChildAccessRead])
def list_access(
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).list_access()


@router.post("", response_model=TeacherChildAccessRead)
def create_access(
    payload: TeacherChildAccessCreate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).create_access(payload, current.id)


@router.patch("/{access_id}", response_model=TeacherChildAccessRead)
def update_access(
    access_id: int,
    payload: TeacherChildAccessUpdate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).update_access(access_id, payload, current.id)


@router.delete("/{access_id}")
def delete_access(
    access_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).delete_access(access_id, current.id)
