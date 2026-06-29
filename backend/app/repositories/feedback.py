from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.models import LessonArtifactFeedback


class LessonArtifactFeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        lesson_id: int,
        artifact_type: str,
        disposition: str,
        child_id: int | None = None,
        teacher_id: int | None = None,
        edit_note: str | None = None,
    ) -> LessonArtifactFeedback:
        feedback = LessonArtifactFeedback(
            lesson_id=lesson_id,
            child_id=child_id,
            teacher_id=teacher_id,
            artifact_type=artifact_type,
            disposition=disposition,
            edit_note=edit_note,
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def list_for_lesson(self, lesson_id: int) -> list[LessonArtifactFeedback]:
        return (
            self.db.query(LessonArtifactFeedback)
            .filter(LessonArtifactFeedback.lesson_id == lesson_id)
            .order_by(LessonArtifactFeedback.id.asc())
            .all()
        )

    def query_for_metrics(
        self,
        child_id: int | None = None,
        goal_id: int | None = None,
        since: datetime | None = None,
    ) -> list[LessonArtifactFeedback]:
        from app.domain.models import LessonPackage

        query = self.db.query(LessonArtifactFeedback)
        if child_id is not None:
            query = query.filter(LessonArtifactFeedback.child_id == child_id)
        if since is not None:
            query = query.filter(LessonArtifactFeedback.created_at >= since)
        if goal_id is not None:
            query = query.join(
                LessonPackage, LessonPackage.id == LessonArtifactFeedback.lesson_id
            ).filter(LessonPackage.goal_id == goal_id)
        return query.all()
