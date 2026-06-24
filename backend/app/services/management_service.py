import json

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.audit import AuditLogRepository
from app.repositories.management import (
    CurriculumContentRepository,
    OrganizationRepository,
    TeacherChildAccessRepository,
    TeacherRepository,
)
from app.schemas.dto import (
    CurriculumContentCreate,
    CurriculumContentRead,
    CurriculumContentUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    TeacherChildAccessCreate,
    TeacherChildAccessRead,
    TeacherChildAccessUpdate,
    TeacherCreate,
    TeacherRead,
    TeacherUpdate,
)


class ManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditLogRepository(db)
        self.organizations = OrganizationRepository(db)
        self.teachers = TeacherRepository(db)
        self.access = TeacherChildAccessRepository(db)
        self.curriculum = CurriculumContentRepository(db)

    def _get_or_404(self, repo, entity_id: int, name: str):
        entity = repo.get(entity_id)
        if not entity:
            raise NotFoundError(f"{name} not found")
        return entity

    def list_organizations(self) -> list[OrganizationRead]:
        return [
            OrganizationRead.model_validate(item) for item in self.organizations.list()
        ]

    def create_organization(
        self, payload: OrganizationCreate, actor_teacher_id: int | None = None
    ) -> OrganizationRead:
        item = self.organizations.create(**payload.model_dump())
        self.audit.write(actor_teacher_id, "create", "Organization", item.id)
        return OrganizationRead.model_validate(item)

    def update_organization(
        self,
        entity_id: int,
        payload: OrganizationUpdate,
        actor_teacher_id: int | None = None,
    ) -> OrganizationRead:
        item = self.organizations.update(
            self._get_or_404(self.organizations, entity_id, "Organization"),
            payload.model_dump(exclude_unset=True),
        )
        self.audit.write(actor_teacher_id, "update", "Organization", item.id)
        return OrganizationRead.model_validate(item)

    def delete_organization(
        self, entity_id: int, actor_teacher_id: int | None = None
    ) -> dict:
        item = self._get_or_404(self.organizations, entity_id, "Organization")
        self.organizations.delete(item)
        self.audit.write(actor_teacher_id, "delete", "Organization", entity_id)
        return {"deleted": True, "id": entity_id}

    def list_teachers(self) -> list[TeacherRead]:
        return [TeacherRead.model_validate(item) for item in self.teachers.list()]

    def create_teacher(
        self, payload: TeacherCreate, actor_teacher_id: int | None = None
    ) -> TeacherRead:
        item = self.teachers.create(**payload.model_dump())
        self.audit.write(actor_teacher_id, "create", "Teacher", item.id)
        return TeacherRead.model_validate(item)

    def update_teacher(
        self,
        entity_id: int,
        payload: TeacherUpdate,
        actor_teacher_id: int | None = None,
    ) -> TeacherRead:
        item = self.teachers.update(
            self._get_or_404(self.teachers, entity_id, "Teacher"),
            payload.model_dump(exclude_unset=True),
        )
        self.audit.write(actor_teacher_id, "update", "Teacher", item.id)
        return TeacherRead.model_validate(item)

    def delete_teacher(
        self, entity_id: int, actor_teacher_id: int | None = None
    ) -> dict:
        item = self._get_or_404(self.teachers, entity_id, "Teacher")
        self.teachers.delete(item)
        self.audit.write(actor_teacher_id, "delete", "Teacher", entity_id)
        return {"deleted": True, "id": entity_id}

    def list_access(self) -> list[TeacherChildAccessRead]:
        return [
            TeacherChildAccessRead.model_validate(item) for item in self.access.list()
        ]

    def create_access(
        self, payload: TeacherChildAccessCreate, actor_teacher_id: int | None = None
    ) -> TeacherChildAccessRead:
        item = self.access.create(**payload.model_dump())
        self.audit.write(
            actor_teacher_id, "create", "TeacherChildAccess", item.id, item.child_id
        )
        return TeacherChildAccessRead.model_validate(item)

    def update_access(
        self,
        entity_id: int,
        payload: TeacherChildAccessUpdate,
        actor_teacher_id: int | None = None,
    ) -> TeacherChildAccessRead:
        item = self.access.update(
            self._get_or_404(self.access, entity_id, "TeacherChildAccess"),
            payload.model_dump(exclude_unset=True),
        )
        self.audit.write(
            actor_teacher_id, "update", "TeacherChildAccess", item.id, item.child_id
        )
        return TeacherChildAccessRead.model_validate(item)

    def delete_access(
        self, entity_id: int, actor_teacher_id: int | None = None
    ) -> dict:
        item = self._get_or_404(self.access, entity_id, "TeacherChildAccess")
        child_id = item.child_id
        self.access.delete(item)
        self.audit.write(
            actor_teacher_id, "delete", "TeacherChildAccess", entity_id, child_id
        )
        return {"deleted": True, "id": entity_id}

    def list_curriculum(self) -> list[CurriculumContentRead]:
        return [self._curriculum_read(item) for item in self.curriculum.list()]

    def get_curriculum(self, entity_id: int) -> CurriculumContentRead:
        return self._curriculum_read(
            self._get_or_404(self.curriculum, entity_id, "Curriculum content")
        )

    def create_curriculum(
        self, payload: CurriculumContentCreate, actor_teacher_id: int | None = None
    ) -> CurriculumContentRead:
        values = payload.model_dump()
        values["content_json"] = json.dumps(values["content_json"])
        item = self.curriculum.create(**values)
        self.audit.write(actor_teacher_id, "create", "CurriculumContent", item.id)
        return self._curriculum_read(item)

    def update_curriculum(
        self,
        entity_id: int,
        payload: CurriculumContentUpdate,
        actor_teacher_id: int | None = None,
    ) -> CurriculumContentRead:
        values = payload.model_dump(exclude_unset=True)
        if "content_json" in values and values["content_json"] is not None:
            values["content_json"] = json.dumps(values["content_json"])
        item = self.curriculum.update(
            self._get_or_404(self.curriculum, entity_id, "Curriculum content"), values
        )
        self.audit.write(actor_teacher_id, "update", "CurriculumContent", item.id)
        return self._curriculum_read(item)

    def delete_curriculum(
        self, entity_id: int, actor_teacher_id: int | None = None
    ) -> dict:
        item = self._get_or_404(self.curriculum, entity_id, "Curriculum content")
        self.curriculum.delete(item)
        self.audit.write(actor_teacher_id, "delete", "CurriculumContent", entity_id)
        return {"deleted": True, "id": entity_id}

    def _curriculum_read(self, item) -> CurriculumContentRead:
        return CurriculumContentRead(
            id=item.id,
            organization_id=item.organization_id,
            title=item.title,
            content_type=item.content_type,
            content_json=json.loads(item.content_json or "{}"),
            status=item.status,
        )
