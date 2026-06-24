from sqlalchemy.orm import Session

from app.domain.models import LessonPackage, SessionRecord


class LessonPackageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, child_id: int, target_skill: str, duration_minutes: int, package_json: str) -> LessonPackage:
        lesson = LessonPackage(
            child_id=child_id,
            target_skill=target_skill,
            duration_minutes=duration_minutes,
            package_json=package_json,
        )
        self.db.add(lesson)
        self.db.commit()
        self.db.refresh(lesson)
        return lesson


class SessionRecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def latest_for_skill(self, child_id: int, target_skill: str) -> SessionRecord | None:
        return (
            self.db.query(SessionRecord)
            .filter(SessionRecord.child_id == child_id, SessionRecord.target_skill == target_skill)
            .order_by(SessionRecord.id.desc())
            .first()
        )

    def create(
        self,
        child_id: int,
        target_skill: str,
        independent_count: int,
        prompted_count: int,
        error_count: int,
        notes: str,
        mastery_level: int,
        progress_delta: int,
        confidence_score: int,
    ) -> SessionRecord:
        record = SessionRecord(
            child_id=child_id,
            target_skill=target_skill,
            independent_count=independent_count,
            prompted_count=prompted_count,
            error_count=error_count,
            notes=notes,
            mastery_level=mastery_level,
            progress_delta=progress_delta,
            confidence_score=confidence_score,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record
