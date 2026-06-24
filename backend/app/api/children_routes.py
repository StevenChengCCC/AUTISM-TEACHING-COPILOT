from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentTeacher,
    get_current_teacher,
    load_teacher,
    require_child_access,
)
from app.core.database import get_db
from app.schemas.dto import (
    ChildProfileCreate,
    ChildProfileRead,
    ChildProfileUpdate,
    ProfileCompletenessResult,
)
from app.services.profile_service import ChildProfileService

router = APIRouter(prefix="/children", tags=["children"])


@router.post("", response_model=ChildProfileRead)
def create_child_profile(
    payload: ChildProfileCreate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    teacher = load_teacher(db, current)
    return ChildProfileService(db).create_child_profile(payload, teacher.id)


@router.get("", response_model=list[ChildProfileRead])
def list_child_profiles(
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    teacher = load_teacher(db, current)
    return ChildProfileService(db).list_for_teacher(
        teacher.id or 0, teacher.organization_id, teacher.is_admin
    )


@router.patch("/{child_id}", response_model=ChildProfileRead)
def update_child_profile(
    child_id: int,
    payload: ChildProfileUpdate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_child_access(db, child_id, current, "editor")
    return ChildProfileService(db).update_child_profile(child_id, payload, current.id)


@router.get("/{child_id}/completeness", response_model=ProfileCompletenessResult)
def check_child_profile_completeness(
    child_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_child_access(db, child_id, current, "viewer")
    return ChildProfileService(db).check_completeness(child_id)
