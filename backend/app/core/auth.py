from dataclasses import dataclass

from fastapi import Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.domain.models import ChildProfile, Teacher, TeacherChildAccess

PERMISSION_RANK = {"viewer": 1, "editor": 2, "admin": 3}


@dataclass(frozen=True)
class CurrentTeacher:
    id: int | None
    role: str = "admin"
    organization_id: int | None = None
    is_anonymous: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def get_current_teacher(
    x_teacher_id: str | None = Header(default=None),
) -> CurrentTeacher:
    if x_teacher_id:
        return CurrentTeacher(id=int(x_teacher_id), role="teacher")
    if settings.DEV_ALLOW_ANON_TEACHER:
        return CurrentTeacher(
            id=settings.DEV_ANON_TEACHER_ID, role="admin", is_anonymous=True
        )
    raise ForbiddenError("Missing X-Teacher-Id header")


def load_teacher(db: Session, current: CurrentTeacher) -> CurrentTeacher:
    if current.is_anonymous:
        return current
    teacher = db.query(Teacher).filter(Teacher.id == current.id).first()
    if not teacher:
        raise ForbiddenError("Teacher not found")
    return CurrentTeacher(
        id=teacher.id, role=teacher.role, organization_id=teacher.organization_id
    )


def require_child_access(
    db: Session, child_id: int, current: CurrentTeacher, permission: str = "viewer"
) -> ChildProfile:
    teacher = load_teacher(db, current)
    child = db.query(ChildProfile).filter(ChildProfile.id == child_id).first()
    if not child:
        raise NotFoundError("Child profile not found")
    if teacher.is_admin and (
        teacher.organization_id is None
        or child.organization_id == teacher.organization_id
    ):
        return child
    access = (
        db.query(TeacherChildAccess)
        .filter(
            TeacherChildAccess.teacher_id == teacher.id,
            TeacherChildAccess.child_id == child_id,
        )
        .first()
    )
    if (
        not access
        or PERMISSION_RANK.get(access.permission_level, 0) < PERMISSION_RANK[permission]
    ):
        raise ForbiddenError("Insufficient child access")
    return child


def require_admin(db: Session, current: CurrentTeacher) -> CurrentTeacher:
    teacher = load_teacher(db, current)
    if not teacher.is_admin:
        raise ForbiddenError("Admin permission required")
    return teacher
