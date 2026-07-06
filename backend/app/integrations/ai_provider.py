from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.config import Settings, settings
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


def get_v2_ai_provider(config: Settings = settings) -> V2AIProvider:
    """Resolve the configured provider without exposing secret values.

    Mock is the safe default. Non-mock providers fail closed rather than silently
    sending learner data through an unintended provider.
    """

    if config.AI_PROVIDER == "mock":
        from app.integrations.mock_ai_provider import MockV2AIProvider

        return MockV2AIProvider()
    if config.AI_PROVIDER == "azure_openai":
        from app.integrations.azure_openai_provider import AzureOpenAIV2Provider

        return AzureOpenAIV2Provider(config)
    raise RuntimeError(
        "Backend v2 OpenAI provider is not enabled; use mock until the safeguarded adapter is implemented"
    )
