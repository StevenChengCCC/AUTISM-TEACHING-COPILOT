from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.models import UploadedMaterial
from app.schemas.dto import UploadedMaterialCreate, UploadedMaterialUpdate


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

    def list(self, child_id: int | None = None) -> list[UploadedMaterial]:
        query = self.db.query(UploadedMaterial)
        if child_id is not None:
            query = query.filter(UploadedMaterial.child_id == child_id)
        return query.order_by(UploadedMaterial.id.desc()).all()

    def get(self, material_id: int) -> UploadedMaterial | None:
        return (
            self.db.query(UploadedMaterial)
            .filter(UploadedMaterial.id == material_id)
            .first()
        )

    def create(self, payload: UploadedMaterialCreate) -> UploadedMaterial:
        material = UploadedMaterial(
            child_id=payload.child_id,
            title=payload.title,
            material_type=payload.material_type,
            source_path=payload.source_path,
            extracted_text=payload.extracted_text,
            status=payload.status,
        )
        self.db.add(material)
        self.db.commit()
        self.db.refresh(material)
        return material

    def update(
        self, material: UploadedMaterial, payload: UploadedMaterialUpdate
    ) -> UploadedMaterial:
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(material, key, value)
        self.db.commit()
        self.db.refresh(material)
        return material

    def delete(self, material: UploadedMaterial) -> None:
        self.db.delete(material)
        self.db.commit()
