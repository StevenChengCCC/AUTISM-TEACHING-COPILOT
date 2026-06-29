from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.domain.models import LessonPackage, SessionRecord


class LessonPackageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        child_id: int,
        target_skill: str,
        duration_minutes: int,
        package_json: str,
        goal_id: int | None = None,
        selected_image_asset_ids: list[int] | None = None,
    ) -> LessonPackage:
        lesson = LessonPackage(
            child_id=child_id,
            goal_id=goal_id,
            target_skill=target_skill,
            duration_minutes=duration_minutes,
            selected_image_asset_ids_json=json.dumps(selected_image_asset_ids or []),
            package_json=package_json,
        )
        self.db.add(lesson)
        self.db.commit()
        self.db.refresh(lesson)
        return lesson

    def update_printable_links(
        self, lesson: LessonPackage, printable_links: dict[str, str]
    ) -> LessonPackage:
        lesson.printable_card_pdf_links_json = json.dumps(printable_links)
        package = json.loads(lesson.package_json)
        package["downloadable_card_pdf_links"] = printable_links
        lesson.package_json = json.dumps(package, ensure_ascii=False)
        self.db.commit()
        self.db.refresh(lesson)
        return lesson


class SessionRecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def latest_for_skill(
        self, child_id: int, target_skill: str, goal_id: int | None = None
    ) -> SessionRecord | None:
        query = self.db.query(SessionRecord).filter(
            SessionRecord.child_id == child_id,
            SessionRecord.target_skill == target_skill,
        )
        if goal_id is not None:
            query = query.filter(SessionRecord.goal_id == goal_id)
        return query.order_by(SessionRecord.id.desc()).first()

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
        goal_id: int | None = None,
    ) -> SessionRecord:
        record = SessionRecord(
            child_id=child_id,
            goal_id=goal_id,
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
