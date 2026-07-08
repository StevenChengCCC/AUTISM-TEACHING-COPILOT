from __future__ import annotations

from typing import Any, NoReturn

from app.core.config import Settings
from app.integrations.ai_provider import V2AIProvider
from app.schemas.v2_dto import (
    AIQuestion,
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraft,
    LessonDesignDraftDto,
)


class AzureOpenAIV2Provider(V2AIProvider):
    """Future Azure OpenAI adapter boundary for Backend v2.

    This class intentionally makes no external calls yet. A production adapter
    will obtain credentials from Managed Identity/Key Vault, apply data-minimum
    prompts and safety controls, and return the same provider contracts.
    """

    def __init__(self, settings: Settings):
        if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_DEPLOYMENT:
            raise RuntimeError("Azure OpenAI endpoint and deployment are required")
        if not settings.reveal(settings.AZURE_OPENAI_API_KEY) and not settings.KEY_VAULT_URL:
            raise RuntimeError("Azure OpenAI secret source is not configured")
        self._settings = settings

    @staticmethod
    def _not_enabled() -> NoReturn:
        raise RuntimeError(
            "Azure OpenAI Backend v2 calls are not enabled until the safety and privacy adapter is implemented"
        )

    def extract_profile(
        self, learner: LearnerProfile, records: list[LearnerRecord]
    ) -> tuple[LearnerProfile, list[str]]:
        return self._not_enabled()

    def generate_lesson_questions(
        self, learner: LearnerProfile, teacher_request: str
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        return self._not_enabled()

    def polish_lesson_brief(self, draft: LessonDesignDraft) -> str:
        return self._not_enabled()

    def generate_lesson_package(
        self, draft: LessonDesignDraftDto
    ) -> dict[str, Any]:
        return self._not_enabled()

    def generate_material_image(
        self,
        learner: LearnerProfile,
        material_type: str,
        prompt: str,
        style: str | None = None,
        size: str | None = None,
    ) -> dict[str, Any]:
        return self._not_enabled()
