import json

from sqlalchemy.orm import Session

from app.domain.models import ChildProfile
from app.schemas.dto import ChildProfileCreate, ChildProfileRead, ChildProfileUpdate


def child_to_read(child: ChildProfile) -> ChildProfileRead:
    return ChildProfileRead(
        id=child.id,
        code=child.code,
        age=child.age,
        diagnosis_level=child.diagnosis_level,
        attention_span_minutes=child.attention_span_minutes,
        communication_mode=child.communication_mode or child.communication_level,
        communication_level=child.communication_level,
        current_level=child.current_level or "",
        interests=json.loads(child.interests_json or "[]"),
        reinforcers=json.loads(child.reinforcers_json or "[]"),
        preferred_reinforcers=json.loads(
            child.preferred_reinforcers_json or child.reinforcers_json or "[]"
        ),
        prompting_that_works=child.prompting_that_works or "",
        avoid_notes=child.avoid_notes or "",
        behavior_notes=child.behavior_notes or "",
        notes=child.notes or "",
    )


class ChildProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, child_id: int) -> ChildProfile | None:
        return self.db.query(ChildProfile).filter(ChildProfile.id == child_id).first()

    def get_by_code(self, code: str) -> ChildProfile | None:
        return self.db.query(ChildProfile).filter(ChildProfile.code == code).first()

    def list(self) -> list[ChildProfile]:
        return self.db.query(ChildProfile).order_by(ChildProfile.id.desc()).all()

    def list_for_teacher(
        self, teacher_id: int, organization_id: int | None, is_admin: bool
    ) -> list[ChildProfile]:
        query = self.db.query(ChildProfile)
        if is_admin and organization_id is not None:
            query = query.filter(ChildProfile.organization_id == organization_id)
        elif not is_admin:
            from app.domain.models import TeacherChildAccess

            query = query.join(
                TeacherChildAccess, TeacherChildAccess.child_id == ChildProfile.id
            ).filter(TeacherChildAccess.teacher_id == teacher_id)
        return query.order_by(ChildProfile.id.desc()).all()

    def create(self, payload: ChildProfileCreate) -> ChildProfile:
        child = ChildProfile(
            code=payload.code,
            age=payload.age,
            diagnosis_level=payload.diagnosis_level,
            attention_span_minutes=payload.attention_span_minutes,
            communication_mode=payload.communication_mode
            or payload.communication_level,
            communication_level=payload.communication_level
            or payload.communication_mode,
            current_level=payload.current_level,
            interests_json=json.dumps(payload.interests, ensure_ascii=False),
            reinforcers_json=json.dumps(payload.reinforcers, ensure_ascii=False),
            preferred_reinforcers_json=json.dumps(
                payload.preferred_reinforcers or payload.reinforcers,
                ensure_ascii=False,
            ),
            prompting_that_works=payload.prompting_that_works,
            avoid_notes=payload.avoid_notes,
            behavior_notes=payload.behavior_notes,
            notes=payload.notes,
        )
        self.db.add(child)
        self.db.commit()
        self.db.refresh(child)
        return child

    def update(self, child: ChildProfile, payload: ChildProfileUpdate) -> ChildProfile:
        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items():
            if key == "interests" and value is not None:
                child.interests_json = json.dumps(value, ensure_ascii=False)
            elif key == "reinforcers" and value is not None:
                child.reinforcers_json = json.dumps(value, ensure_ascii=False)
            elif key == "preferred_reinforcers" and value is not None:
                child.preferred_reinforcers_json = json.dumps(value, ensure_ascii=False)
            else:
                setattr(child, key, value)
        self.db.commit()
        self.db.refresh(child)
        return child
