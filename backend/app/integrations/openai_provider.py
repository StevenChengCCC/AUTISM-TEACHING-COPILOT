from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.core.config import Settings, settings
from app.core.exceptions import AIInvalidOutputError, AIProviderFailureError
from app.integrations.ai_provider import V2AIProvider
from app.schemas.v2_dto import (
    AIQuestion,
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraft,
    LessonDesignDraftDto,
    ProfileExtractionResult,
    ProfileSignal,
)
from app.services.v2_ai_context_service import build_ai_safe_profile
from app.skills.models import PromptEnvelope
from app.skills.prompt_builder import PromptBuilder
from app.skills.registry import SkillRegistry, get_skill_registry


class _OpenAIOutputError(ValueError):
    """Model output was returned but did not match the provider contract."""


class _OpenAIRequestError(RuntimeError):
    """A sanitized vendor request failure safe to handle at the provider boundary."""


logger = logging.getLogger(__name__)


class OpenAIV2AIProvider(V2AIProvider):
    """OpenAI-backed v2 boundary with lazy credentials and deterministic fallback.

    Services consume the same typed contract as the mock provider. Only this module
    knows about the vendor SDK, which keeps later safety and prompt changes local.
    """

    provider_name = "openai"

    def __init__(
        self,
        config: Settings = settings,
        client: Any | None = None,
        registry: SkillRegistry | None = None,
    ) -> None:
        from app.integrations.mock_ai_provider import MockV2AIProvider

        self._settings = config
        self._client = client
        self._registry = registry or get_skill_registry(config)
        self._prompts = PromptBuilder()
        self._fallback = MockV2AIProvider(config=config, registry=self._registry)
        self.last_fallback_used = False
        self.last_generation_metadata = None
        self.generation_metadata_by_skill = {}

    def _get_client(self) -> Any:
        """Create the SDK client only when an OpenAI operation is attempted."""

        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._settings.require_openai_api_key(),
                timeout=self._settings.OPENAI_TIMEOUT_SECONDS,
            )
        return self._client

    @staticmethod
    def _decode_json(content: str | None) -> dict[str, Any]:
        if not content:
            raise _OpenAIOutputError("The model returned no content")
        value = content.strip()
        if value.startswith("```"):
            lines = value.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            value = "\n".join(lines).strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise _OpenAIOutputError("The model returned malformed JSON") from exc
        if not isinstance(parsed, dict):
            raise _OpenAIOutputError("The model response must be a JSON object")
        return parsed

    def _request_json(
        self,
        prompt: PromptEnvelope,
        response_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        # Resolve configuration before the vendor call so the deliberate, safe
        # missing-key error remains distinct from SDK/network failures.
        client = self._get_client()
        try:
            if response_model is not None:
                response = client.responses.parse(
                    model=self._settings.OPENAI_TEXT_MODEL,
                    instructions=prompt.system_instructions,
                    input=prompt.user_input,
                    text_format=response_model,
                )
            else:
                response = client.responses.create(
                    model=self._settings.OPENAI_TEXT_MODEL,
                    instructions=prompt.system_instructions,
                    input=prompt.user_input,
                    text={"format": {"type": "json_object"}},
                )
        except ValidationError as exc:
            raise _OpenAIOutputError(
                "The model response did not match the required schema"
            ) from exc
        except Exception as exc:
            # Do not leak credentials, learner content, or vendor response details.
            raise _OpenAIRequestError(
                "OpenAI request failed. Check backend provider configuration and try again."
            ) from exc
        if response_model is not None:
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise _OpenAIOutputError(
                    "The model returned no schema-compatible content"
                )
            if not isinstance(parsed, response_model):
                raise _OpenAIOutputError(
                    "The model returned an unexpected parsed response type"
                )
            return parsed.model_dump(mode="json", by_alias=True)
        try:
            content = response.output_text
        except (AttributeError, TypeError) as exc:
            raise _OpenAIOutputError(
                "The model response had an unexpected shape"
            ) from exc
        return self._decode_json(content)

    def _mark_fallback(self, operation: str, skill_id: str, failure_kind: str) -> None:
        self.last_fallback_used = True
        self._record_generation(
            self._registry,
            skill_id,
            status="local_mock",
            model=self._settings.OPENAI_TEXT_MODEL,
            output_source="mock_fallback",
        )
        if skill_id == "lesson_generation":
            self._record_generation(
                self._registry,
                "material_generation",
                status="local_mock",
                model=self._settings.OPENAI_TEXT_MODEL,
                output_source="mock_fallback",
                set_last=False,
            )
        logger.warning(
            "AI operation %s could not complete (%s); using local mock fallback",
            operation,
            failure_kind,
        )

    def _handle_provider_failure(
        self, operation: str, skill_id: str, failure_kind: str
    ) -> None:
        if self._settings.effective_ai_failure_mode == "fail_closed":
            logger.error(
                "AI provider operation unavailable",
                extra={
                    "event": failure_kind,
                    "error_code": failure_kind,
                },
            )
            if failure_kind == "invalid_output":
                raise AIInvalidOutputError(
                    "AI generation is temporarily unavailable because the returned content could not be validated. Please retry."
                )
            raise AIProviderFailureError(
                "AI generation is temporarily unavailable. Please try again later."
            )
        self._mark_fallback(operation, skill_id, failure_kind)

    def _success(self, skill_id: str) -> None:
        self._record_generation(
            self._registry,
            skill_id,
            status="ready",
            model=self._settings.OPENAI_TEXT_MODEL,
            output_source="provider",
        )

    @staticmethod
    def _failure_kind(exc: Exception) -> str:
        return (
            "provider_failure"
            if isinstance(exc, _OpenAIRequestError)
            else "invalid_output"
        )

    @staticmethod
    def _validate_question_groups(questions: list[AIQuestion]) -> None:
        question_ids = {question.id for question in questions}
        required_ids = {
            "target-response",
            "baseline",
            "response-level",
            "scenarios",
            "materials",
            "data-collection",
            "duration",
            "prompting-limits",
        }
        if not required_ids.issubset(question_ids):
            raise _OpenAIOutputError("Required lesson question groups were missing")

    def extract_profile(
        self, learner: LearnerProfile, records: list[LearnerRecord]
    ) -> ProfileExtractionResult:
        self.last_fallback_used = False
        payload = {
            "learner": build_ai_safe_profile(learner),
            "records": [
                {"recordId": record.id, "untrustedText": record.extracted_text}
                for record in records
            ],
        }
        try:
            skill = self._registry.get("learner_profile")
            result = self._request_json(
                self._prompts.build(
                    skill,
                    output_contract={
                        "learner": "LearnerProfile-compatible object",
                        "profileSignals": "array of evidence-linked signals",
                        "unknownFields": "array of field names",
                        "insights": "array of short strings",
                    },
                    trusted_input={"learner": payload["learner"]},
                    untrusted_input={"records": payload["records"]},
                ),
                ProfileExtractionResult,
            )
            extracted_values = result["learner"]
            if not isinstance(extracted_values, dict):
                raise _OpenAIOutputError("Learner extraction must be an object")
            preserved = learner.model_dump()
            preserved.update(extracted_values)
            preserved["id"] = learner.id
            preserved["code"] = learner.code
            extracted = LearnerProfile.model_validate(preserved)
            insights = result["insights"]
            if not isinstance(insights, list) or not all(
                isinstance(item, str) for item in insights
            ):
                raise _OpenAIOutputError("Insights must be a list of strings")
            signals = [
                ProfileSignal.model_validate(item)
                for item in result.get("profileSignals", [])
            ]
            unknown_fields = result.get("unknownFields", [])
            if not isinstance(unknown_fields, list) or not all(
                isinstance(item, str) for item in unknown_fields
            ):
                raise _OpenAIOutputError("unknownFields must be a list of strings")
            extracted.profile_signals = signals
            extracted.unknown_fields = unknown_fields
            self._success("learner_profile")
            return ProfileExtractionResult(
                learner=extracted,
                profileSignals=signals,
                unknownFields=unknown_fields,
                insights=insights,
            )
        except (
            _OpenAIOutputError,
            _OpenAIRequestError,
            ValidationError,
            KeyError,
            TypeError,
        ) as exc:
            self._handle_provider_failure(
                "profile extraction", "learner_profile", self._failure_kind(exc)
            )
            return self._fallback.extract_profile(learner, records)

    def generate_lesson_questions(
        self, learner: LearnerProfile, teacher_request: str
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        self.last_fallback_used = False
        try:
            skill = self._registry.get("lesson_planning")
            result = self._request_json(
                self._prompts.build(
                    skill,
                    output_contract={
                        "questions": "a concise dynamic list of required and conditional AIQuestion-compatible objects",
                        "draft": "LessonDesignDraft-compatible object",
                    },
                    trusted_input={"learner": build_ai_safe_profile(learner)},
                    untrusted_input={"teacherRequest": teacher_request},
                )
            )
            questions = [
                AIQuestion.model_validate(question) for question in result["questions"]
            ]
            self._validate_question_groups(questions)
            draft = LessonDesignDraft.model_validate(result["draft"])
            draft.learner_id = learner.id
            self._success("lesson_planning")
            return questions, draft
        except (
            _OpenAIOutputError,
            _OpenAIRequestError,
            ValidationError,
            KeyError,
            TypeError,
        ) as exc:
            self._handle_provider_failure(
                "lesson question generation", "lesson_planning", self._failure_kind(exc)
            )
            return self._fallback.generate_lesson_questions(learner, teacher_request)

    def polish_lesson_brief(self, draft: LessonDesignDraft) -> str:
        self.last_fallback_used = False
        try:
            skill = self._registry.get("lesson_generation")
            result = self._request_json(
                self._prompts.build(
                    skill,
                    output_contract={"lessonBrief": "non-empty string"},
                    trusted_input={"draft": draft.model_dump(by_alias=True)},
                )
            )
            brief = result["lessonBrief"]
            if not isinstance(brief, str) or not brief.strip():
                raise _OpenAIOutputError("lessonBrief must be a non-empty string")
            self._success("lesson_generation")
            return brief.strip()
        except (_OpenAIOutputError, _OpenAIRequestError, KeyError, TypeError) as exc:
            self._handle_provider_failure(
                "lesson brief polishing", "lesson_generation", self._failure_kind(exc)
            )
            return self._fallback.polish_lesson_brief(draft)

    def generate_lesson_package(
        self,
        draft: LessonDesignDraftDto,
        learner_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.last_fallback_used = False
        try:
            lesson_skill = self._registry.get("lesson_generation")
            material_skill = self._registry.get("material_generation")
            prompt = self._prompts.build(
                lesson_skill,
                output_contract={
                    "lessonBrief": "non-empty string",
                    "summaryTemplate": "non-empty string",
                    "teachingFlow": "array of TeachingStep objects",
                    "materials": "array of selected material definitions with type title content",
                },
                trusted_input={
                    "draft": draft.model_dump(by_alias=True),
                    "learnerContext": learner_context or {},
                },
                supplemental_skills=(material_skill,),
            )
            result = self._request_json(prompt)
            lesson_brief = result["lessonBrief"]
            summary_template = result["summaryTemplate"]
            if not all(
                isinstance(value, str) and value.strip()
                for value in (lesson_brief, summary_template)
            ):
                raise _OpenAIOutputError("Package copy must contain non-empty strings")
            generated: dict[str, Any] = {
                "lessonBrief": lesson_brief.strip(),
                "summaryTemplate": summary_template.strip(),
            }
            suggestions = result.get("materialCopySuggestions")
            if isinstance(suggestions, dict):
                generated["materialCopySuggestions"] = suggestions
            if isinstance(result.get("teachingFlow"), list):
                generated["teachingFlow"] = result["teachingFlow"]
            if isinstance(result.get("materials"), list):
                generated["materials"] = result["materials"]
            self._success("lesson_generation")
            self._record_generation(
                self._registry,
                "material_generation",
                status="ready",
                model=self._settings.OPENAI_TEXT_MODEL,
                output_source="provider",
                set_last=False,
            )
            return generated
        except (_OpenAIOutputError, _OpenAIRequestError, KeyError, TypeError) as exc:
            self._handle_provider_failure(
                "lesson package generation",
                "lesson_generation",
                self._failure_kind(exc),
            )
            return self._fallback.generate_lesson_package(draft, learner_context)

    def generate_material_image(
        self,
        learner: LearnerProfile,
        material_type: str,
        prompt: str,
        style: str | None = None,
        size: str | None = None,
    ) -> dict[str, Any]:
        self.last_fallback_used = False
        requested_size = size or "1024x1024"
        allowed_sizes = {"1024x1024", "1536x1024", "1024x1536", "auto"}
        if requested_size not in allowed_sizes:
            requested_size = "1024x1024"
        prompt_used = prompt.strip()
        if style and style.strip():
            prompt_used = f"{prompt_used} Style: {style.strip()}."
        skill = self._registry.get("image_generation")
        envelope = self._prompts.build(
            skill,
            output_contract={"image": "PNG educational illustration"},
            trusted_input={"materialType": material_type, "style": style or ""},
            untrusted_input={"requestedConcept": prompt_used},
        )
        safe_prompt = f"{envelope.system_instructions}\n\n{envelope.user_input}"
        try:
            client = self._get_client()
            try:
                response = client.images.generate(
                    model=self._settings.OPENAI_IMAGE_MODEL,
                    prompt=safe_prompt,
                    size=requested_size,
                    output_format="png",
                    n=1,
                )
            except Exception as exc:
                raise _OpenAIRequestError(
                    "OpenAI image request failed. Check backend provider configuration and try again."
                ) from exc
            if not response.data:
                raise _OpenAIOutputError("The image model returned no image")
            image = response.data[0]
            image_base64 = getattr(image, "b64_json", None)
            image_url = getattr(image, "url", None)
            if not image_base64 and not image_url:
                raise _OpenAIOutputError("The image model returned unusable image data")
            self._record_generation(
                self._registry,
                "image_generation",
                status="ready",
                model=self._settings.OPENAI_IMAGE_MODEL,
                output_source="provider",
            )
            return {
                "imageId": f"image-{uuid4().hex}",
                "status": "ready",
                "imageUrl": image_url,
                "imageBase64": image_base64,
                "promptUsed": prompt_used,
                "fallbackUsed": False,
            }
        except (_OpenAIOutputError, _OpenAIRequestError) as exc:
            self._handle_provider_failure(
                "material image generation", "image_generation", self._failure_kind(exc)
            )
            fallback = self._fallback.generate_material_image(
                learner, material_type, prompt, style, requested_size
            )
            fallback["fallbackUsed"] = True
            return fallback
