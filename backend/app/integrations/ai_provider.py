from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.v2_dto import (
    AIQuestion,
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraft,
    LessonDesignDraftDto,
)


class V2AIProvider(ABC):
    """Replaceable v2 AI boundary; services never depend on an AI vendor SDK."""

    @abstractmethod
    def extract_profile(
        self, learner: LearnerProfile, records: list[LearnerRecord]
    ) -> tuple[LearnerProfile, list[str]]:
        raise NotImplementedError

    @abstractmethod
    def generate_lesson_questions(
        self, learner: LearnerProfile, teacher_request: str
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        raise NotImplementedError

    def build_lesson_questions(
        self, learner: LearnerProfile, teacher_request: str
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        """Compatibility alias for earlier Backend v2 callers."""

        return self.generate_lesson_questions(learner, teacher_request)

    @abstractmethod
    def polish_lesson_brief(self, draft: LessonDesignDraft) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_lesson_package(
        self, draft: LessonDesignDraftDto
    ) -> dict[str, Any]:
        """Return provider-authored content; orchestration stays in the service."""

        raise NotImplementedError
