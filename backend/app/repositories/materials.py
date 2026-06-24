from sqlalchemy.orm import Session

from app.domain.models import UploadedMaterial
from app.schemas.dto import UploadedMaterialCreate


class UploadedMaterialRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_child(self, child_id: int) -> list[UploadedMaterial]:
        return (
            self.db.query(UploadedMaterial)
            .filter(UploadedMaterial.child_id == child_id)
            .order_by(UploadedMaterial.id.desc())
            .all()
        )

    def create(self, payload: UploadedMaterialCreate) -> UploadedMaterial:
        material = UploadedMaterial(
            child_id=payload.child_id,
            title=payload.title,
            material_type=payload.material_type,
            source_path=payload.source_path,
            extracted_text=payload.extracted_text,
        )
        self.db.add(material)
        self.db.commit()
        self.db.refresh(material)
        return material
