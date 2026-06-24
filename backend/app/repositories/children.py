import json

from sqlalchemy.orm import Session

from app.domain.models import ChildProfile
from app.schemas.dto import ChildProfileCreate, ChildProfileRead


def child_to_read(child: ChildProfile) -> ChildProfileRead:
    return ChildProfileRead(
        id=child.id,
        code=child.code,
        age=child.age,
        diagnosis_level=child.diagnosis_level,
        attention_span_minutes=child.attention_span_minutes,
        communication_level=child.communication_level,
        interests=json.loads(child.interests_json or "[]"),
        reinforcers=json.loads(child.reinforcers_json or "[]"),
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

    def create(self, payload: ChildProfileCreate) -> ChildProfile:
        child = ChildProfile(
            code=payload.code,
            age=payload.age,
            diagnosis_level=payload.diagnosis_level,
            attention_span_minutes=payload.attention_span_minutes,
            communication_level=payload.communication_level,
            interests_json=json.dumps(payload.interests, ensure_ascii=False),
            reinforcers_json=json.dumps(payload.reinforcers, ensure_ascii=False),
            behavior_notes=payload.behavior_notes,
            notes=payload.notes,
        )
        self.db.add(child)
        self.db.commit()
        self.db.refresh(child)
        return child
