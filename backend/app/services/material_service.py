from sqlalchemy.orm import Session
from pathlib import Path

from app.core.exceptions import NotFoundError, ValidationError
from app.core.privacy import scan_pii
from app.repositories.audit import AuditLogRepository
from app.repositories.children import ChildProfileRepository
from app.repositories.materials import UploadedMaterialRepository
from app.schemas.dto import (
    UploadedMaterialCreate,
    UploadedMaterialRead,
    UploadedMaterialUpdate,
)


class UploadedMaterialService:
    def __init__(self, db: Session):
        self.children = ChildProfileRepository(db)
        self.materials = UploadedMaterialRepository(db)

    def list(self, child_id: int | None = None) -> list[UploadedMaterialRead]:
        materials = self.materials.list(child_id)
        return [UploadedMaterialRead.model_validate(material) for material in materials]

    def list_for_child(self, child_id: int) -> list[UploadedMaterialRead]:
        if not self.children.get(child_id):
            raise NotFoundError("Child profile not found")
        return self.list(child_id)

    def get(self, material_id: int) -> UploadedMaterialRead:
        material = self.materials.get(material_id)
        if not material:
            raise NotFoundError("Uploaded material not found")
        return UploadedMaterialRead.model_validate(material)

    def create(
        self, payload: UploadedMaterialCreate, actor_teacher_id: int | None = None
    ) -> UploadedMaterialRead:
        if not self.children.get(payload.child_id):
            raise NotFoundError("Child profile not found")
        payload = self._extract_supported_text(payload)
        self._validate_material_text(payload.extracted_text)
        material = self.materials.create(payload)
        AuditLogRepository(self.materials.db).write(
            actor_teacher_id,
            "create",
            "UploadedMaterial",
            material.id,
            material.child_id,
        )
        return UploadedMaterialRead.model_validate(material)

    def update(
        self,
        material_id: int,
        payload: UploadedMaterialUpdate,
        actor_teacher_id: int | None = None,
    ) -> UploadedMaterialRead:
        material = self.materials.get(material_id)
        if not material:
            raise NotFoundError("Uploaded material not found")
        if payload.extracted_text is not None:
            self._validate_material_text(payload.extracted_text)
        updated = self.materials.update(material, payload)
        AuditLogRepository(self.materials.db).write(
            actor_teacher_id, "update", "UploadedMaterial", updated.id, updated.child_id
        )
        return UploadedMaterialRead.model_validate(updated)

    def delete(self, material_id: int, actor_teacher_id: int | None = None) -> dict:
        material = self.materials.get(material_id)
        if not material:
            raise NotFoundError("Uploaded material not found")
        child_id = material.child_id
        self.materials.delete(material)
        AuditLogRepository(self.materials.db).write(
            actor_teacher_id, "delete", "UploadedMaterial", material_id, child_id
        )
        return {"deleted": True, "id": material_id}

    def _validate_material_text(self, text: str) -> None:
        findings = scan_pii(text)
        if findings:
            raise ValidationError(
                "Uploaded material text appears to contain direct identifiers.",
                {"pii_findings": findings},
            )

    def _extract_supported_text(
        self, payload: UploadedMaterialCreate
    ) -> UploadedMaterialCreate:
        if payload.extracted_text or not payload.source_path:
            return payload
        path = Path(payload.source_path)
        if path.suffix.lower() not in {".txt", ".md"} or not path.exists():
            return payload
        return payload.model_copy(
            update={
                "extracted_text": path.read_text(encoding="utf-8", errors="ignore"),
                "status": "extracted",
            }
        )
