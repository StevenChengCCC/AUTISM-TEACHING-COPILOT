from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.privacy import is_pseudonymous_child_code, scan_pii
from app.repositories.audit import AuditLogRepository
from app.repositories.children import ChildProfileRepository, child_to_read
from app.schemas.dto import (
    ChildProfileCreate,
    ChildProfileRead,
    ChildProfileUpdate,
    ProfileCompletenessResult,
)
from app.services.profile_completeness_service import ProfileCompletenessService


class ChildProfileService:
    def __init__(self, db: Session):
        self.children = ChildProfileRepository(db)

    def create_child_profile(
        self, payload: ChildProfileCreate, actor_teacher_id: int | None = None
    ) -> ChildProfileRead:
        if not is_pseudonymous_child_code(payload.code):
            raise ValidationError(
                "Child code must be pseudonymous and contain only letters, numbers, dashes, or underscores."
            )
        self._validate_no_pii([payload.behavior_notes, payload.notes])
        if self.children.get_by_code(payload.code):
            raise ConflictError("Child code already exists")
        child = self.children.create(payload)
        AuditLogRepository(self.children.db).write(
            actor_teacher_id, "create", "ChildProfile", child.id, child.id
        )
        return child_to_read(child)

    def list_child_profiles(self) -> list[ChildProfileRead]:
        return [child_to_read(child) for child in self.children.list_all()]

    def list_for_teacher(
        self, teacher_id: int, organization_id: int | None, is_admin: bool
    ) -> list[ChildProfileRead]:
        return [
            child_to_read(child)
            for child in self.children.list_for_teacher(
                teacher_id, organization_id, is_admin
            )
        ]

    def update_child_profile(
        self,
        child_id: int,
        payload: ChildProfileUpdate,
        actor_teacher_id: int | None = None,
    ) -> ChildProfileRead:
        child = self.children.get(child_id)
        if not child:
            raise NotFoundError("Child profile not found")
        self._validate_no_pii([payload.behavior_notes, payload.notes])
        updated = self.children.update(child, payload)
        AuditLogRepository(self.children.db).write(
            actor_teacher_id, "update", "ChildProfile", child_id, child_id
        )
        return child_to_read(updated)

    def check_completeness(self, child_id: int) -> ProfileCompletenessResult:
        from app.core.exceptions import NotFoundError

        child = self.children.get(child_id)
        if not child:
            raise NotFoundError("Child profile not found")
        return ProfileCompletenessService().check(child)

    def _validate_no_pii(self, values: list[str | None]) -> None:
        findings = sorted({item for value in values for item in scan_pii(value)})
        if findings:
            raise ValidationError(
                "Child profile text appears to contain direct identifiers.",
                {"pii_findings": findings},
            )
