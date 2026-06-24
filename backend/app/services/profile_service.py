from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.repositories.children import ChildProfileRepository, child_to_read
from app.schemas.dto import (
    ChildProfileCreate,
    ChildProfileRead,
    ProfileCompletenessResult,
)
from app.services.profile_completeness_service import ProfileCompletenessService


class ChildProfileService:
    def __init__(self, db: Session):
        self.children = ChildProfileRepository(db)

    def create_child_profile(self, payload: ChildProfileCreate) -> ChildProfileRead:
        if self.children.get_by_code(payload.code):
            raise ConflictError("Child code already exists")
        return child_to_read(self.children.create(payload))

    def list_child_profiles(self) -> list[ChildProfileRead]:
        return [child_to_read(child) for child in self.children.list()]

    def check_completeness(self, child_id: int) -> ProfileCompletenessResult:
        from app.core.exceptions import NotFoundError

        child = self.children.get(child_id)
        if not child:
            raise NotFoundError("Child profile not found")
        return ProfileCompletenessService().check(child)
