from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_admin
from app.core.database import get_db
from app.schemas.dto import TeacherCreate, TeacherRead, TeacherUpdate
from app.services.management_service import ManagementService

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("", response_model=list[TeacherRead])
def list_teachers(
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).list_teachers()


@router.post("", response_model=TeacherRead)
def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).create_teacher(payload, current.id)


@router.patch("/{teacher_id}", response_model=TeacherRead)
def update_teacher(
    teacher_id: int,
    payload: TeacherUpdate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).update_teacher(teacher_id, payload, current.id)


@router.delete("/{teacher_id}")
def delete_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).delete_teacher(teacher_id, current.id)
