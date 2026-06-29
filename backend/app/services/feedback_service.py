from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.domain.models import LessonPackage
from app.repositories.audit import AuditLogRepository
from app.repositories.feedback import LessonArtifactFeedbackRepository
from app.schemas.dto import (
    ARTIFACT_TYPES,
    DISPOSITIONS,
    ArtifactFeedbackRead,
    ArtifactFeedbackSubmit,
    DirectUseMetrics,
    DispositionCounts,
)


class LessonFeedbackService:
    def __init__(self, db: Session):
        self.db = db
        self.feedback = LessonArtifactFeedbackRepository(db)

    def _get_lesson(self, lesson_id: int) -> LessonPackage:
        lesson = (
            self.db.query(LessonPackage)
            .filter(LessonPackage.id == lesson_id)
            .first()
        )
        if not lesson:
            raise NotFoundError("Lesson package not found")
        return lesson

    def submit_feedback(
        self,
        lesson_id: int,
        payload: ArtifactFeedbackSubmit,
        actor_teacher_id: int | None = None,
    ) -> list[ArtifactFeedbackRead]:
        lesson = self._get_lesson(lesson_id)
        if not payload.items:
            raise ValidationError("At least one feedback item is required.")
        for item in payload.items:
            if item.artifact_type not in ARTIFACT_TYPES:
                raise ValidationError(
                    f"Unknown artifact_type '{item.artifact_type}'.",
                    {"allowed_artifact_types": sorted(ARTIFACT_TYPES)},
                )
            if item.disposition not in DISPOSITIONS:
                raise ValidationError(
                    f"Unknown disposition '{item.disposition}'.",
                    {"allowed_dispositions": sorted(DISPOSITIONS)},
                )

        created = [
            self.feedback.create(
                lesson_id=lesson.id,
                artifact_type=item.artifact_type,
                disposition=item.disposition,
                child_id=lesson.child_id,
                teacher_id=actor_teacher_id,
                edit_note=item.edit_note,
            )
            for item in payload.items
        ]
        AuditLogRepository(self.db).write(
            actor_teacher_id,
            "create",
            "LessonArtifactFeedback",
            lesson.id,
            lesson.child_id,
            {"item_count": len(created)},
        )
        return [ArtifactFeedbackRead.model_validate(row) for row in created]

    def list_feedback(self, lesson_id: int) -> list[ArtifactFeedbackRead]:
        self._get_lesson(lesson_id)
        return [
            ArtifactFeedbackRead.model_validate(row)
            for row in self.feedback.list_for_lesson(lesson_id)
        ]

    def direct_use_metrics(
        self,
        child_id: int | None = None,
        goal_id: int | None = None,
        since: datetime | None = None,
    ) -> DirectUseMetrics:
        rows = self.feedback.query_for_metrics(child_id, goal_id, since)
        overall = DispositionCounts()
        by_type: dict[str, DispositionCounts] = {}
        for row in rows:
            bucket = by_type.setdefault(row.artifact_type, DispositionCounts())
            if hasattr(overall, row.disposition):
                setattr(overall, row.disposition, getattr(overall, row.disposition) + 1)
                setattr(bucket, row.disposition, getattr(bucket, row.disposition) + 1)
        total = overall.used_as_is + overall.edited + overall.not_used
        rate = (overall.used_as_is / total) if total else 0.0
        return DirectUseMetrics(
            direct_use_rate=rate,
            total_rated=total,
            by_disposition=overall,
            by_artifact_type=by_type,
        )
