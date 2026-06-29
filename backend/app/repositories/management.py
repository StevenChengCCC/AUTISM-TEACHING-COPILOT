from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.models import (
    CurriculumContent,
    Organization,
    Teacher,
    TeacherChildAccess,
)


class CrudRepository:
    model = None

    def __init__(self, db: Session):
        self.db = db

    def list(self):
        return self.db.query(self.model).order_by(self.model.id.desc()).all()

    def get(self, entity_id: int):
        return self.db.query(self.model).filter(self.model.id == entity_id).first()

    def create(self, **values):
        entity = self.model(**values)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update(self, entity, values: dict):
        for key, value in values.items():
            setattr(entity, key, value)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity) -> None:
        self.db.delete(entity)
        self.db.commit()


class OrganizationRepository(CrudRepository):
    model = Organization


class TeacherRepository(CrudRepository):
    model = Teacher


class TeacherChildAccessRepository(CrudRepository):
    model = TeacherChildAccess


class CurriculumContentRepository(CrudRepository):
    model = CurriculumContent
