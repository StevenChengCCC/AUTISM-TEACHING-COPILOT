from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.children import ChildProfileRepository
from app.repositories.materials import UploadedMaterialRepository
from app.schemas.dto import UploadedMaterialCreate, UploadedMaterialRead


class UploadedMaterialService:
    def __init__(self, db: Session):
        self.children = ChildProfileRepository(db)
        self.materials = UploadedMaterialRepository(db)

    def list_for_child(self, child_id: int) -> list[UploadedMaterialRead]:
        if not self.children.get(child_id):
            raise NotFoundError("Child profile not found")
        return [
            UploadedMaterialRead.model_validate(material)
            for material in self.materials.list_for_child(child_id)
        ]

    def create(self, payload: UploadedMaterialCreate) -> UploadedMaterialRead:
        if not self.children.get(payload.child_id):
            raise NotFoundError("Child profile not found")
        return UploadedMaterialRead.model_validate(self.materials.create(payload))
