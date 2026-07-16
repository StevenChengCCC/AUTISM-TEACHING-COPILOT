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
    ProfileExtractionResult,
)
from app.skills.models import GenerationMetadata
from app.skills.registry import SkillRegistry, get_skill_registry


class V2AIProvider(ABC):
    """Replaceable v2 AI boundary; services never depend on an AI vendor SDK."""

    provider_name = "unknown"
    last_generation_metadata: GenerationMetadata | None = None
    generation_metadata_by_skill: dict[str, GenerationMetadata]

    def _record_generation(
        self,
        registry: SkillRegistry,
        skill_id: str,
        *,
        status: str,
        model: str,
        output_source: str,
        set_last: bool = True,
    ) -> GenerationMetadata:
        metadata = GenerationMetadata.from_skill(
            registry.get(skill_id),
            status=status,  # type: ignore[arg-type]
            provider=self.provider_name,
            model=model,
            output_source=output_source,  # type: ignore[arg-type]
        )
        if not hasattr(self, "generation_metadata_by_skill"):
            self.generation_metadata_by_skill = {}
        self.generation_metadata_by_skill[skill_id] = metadata
        if set_last:
            self.last_generation_metadata = metadata
        return metadata

    @abstractmethod
    def extract_profile(
        self, learner: LearnerProfile, records: list[LearnerRecord]
    ) -> ProfileExtractionResult:
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
        self,
        draft: LessonDesignDraftDto,
        learner_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return provider-authored content; orchestration stays in the service."""

        raise NotImplementedError

    @abstractmethod
    def generate_material_image(
        self,
        learner: LearnerProfile,
        material_type: str,
        prompt: str,
        style: str | None = None,
        size: str | None = None,
    ) -> dict[str, Any]:
        """Generate dev-test image output behind the same provider boundary."""

        raise NotImplementedError


def get_v2_ai_provider(
    config: Settings = settings, registry: SkillRegistry | None = None
) -> V2AIProvider:
    """Resolve the configured provider without exposing secret values.

    Mock is the safe default. Non-mock providers fail closed rather than silently
    sending learner data through an unintended provider.
    """

    skill_registry = registry or get_skill_registry(config)
    if config.AI_PROVIDER == "mock":
        from app.integrations.mock_ai_provider import MockV2AIProvider

        return MockV2AIProvider(config=config, registry=skill_registry)
    if config.AI_PROVIDER == "azure_openai":
        from app.integrations.azure_openai_provider import AzureOpenAIV2Provider

        return AzureOpenAIV2Provider(config)
    if config.AI_PROVIDER == "openai":
        from app.integrations.openai_provider import OpenAIV2AIProvider

        return OpenAIV2AIProvider(config, registry=skill_registry)
    raise RuntimeError(f"Unsupported AI_PROVIDER: {config.AI_PROVIDER}")
