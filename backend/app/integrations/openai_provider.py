from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings, settings
from app.core.exceptions import AIInvalidOutputError, AIProviderFailureError
from app.integrations.ai_provider import V2AIProvider
from app.schemas.v2_dto import (
    AIQuestion,
    AIQuestionOption,
    CanonicalLearnerProfile,
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraft,
    LessonSpec,
    MaterialSpec,
    MaterialValidationIssue,
    ProfileExtractionResult,
    InstructionalConstraintSnapshot,
)
from app.services.v2_ai_context_service import build_ai_safe_profile
from app.services.v2_profile_normalization_service import canonicalize_profile
from app.skills.models import PromptEnvelope
from app.skills.prompt_builder import PromptBuilder
from app.skills.registry import SkillRegistry, get_skill_registry


class _OpenAIOutputError(ValueError):
    """Model output was returned but did not match the provider contract."""


class _OpenAIRequestError(RuntimeError):
    """A sanitized vendor request failure safe to handle at the provider boundary."""


class _LessonSectionRevision(BaseModel):
    revisedText: str


class _TeachingStepCopyTransport(BaseModel):
    """Provider-authored classroom copy with no open-ended JSON fields."""

    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    description: str
    duration: str
    teacherAction: str
    learnerAction: str
    teacherScript: str
    expectedLearnerResponse: str
    waitTime: str
    promptAction: str
    reinforcementAction: str
    errorCorrectionAction: str
    dataToRecord: list[str]
    transitionCue: str
    breakOption: str


class _LessonPackageCopyTransport(BaseModel):
    """Small AI boundary; typed material semantics are projected locally."""

    model_config = ConfigDict(extra="forbid")
    lessonBrief: str
    summaryTemplate: str
    teachingFlow: list[_TeachingStepCopyTransport] = Field(
        min_length=3, max_length=6
    )


class _PlanningOptionTransport(BaseModel):
    """Compact provider-only option; domain provenance is projected locally."""

    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    value: str
    description: str
    recommended: bool
    reason: str
    profileFactorIds: list[str]
    assumptions: list[str]


class _PlanningQuestionTransport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    prompt: str
    helperText: str
    field: Literal["goalText", "scenarios", "selectedMaterials"]
    inputType: Literal["single_select", "multi_select", "hybrid"]
    options: list[_PlanningOptionTransport] = Field(min_length=1, max_length=3)
    allowCustomAnswer: bool
    maxSelections: int | None


class _LessonPlanningTransport(BaseModel):
    """Small AI boundary for the three strong teacher-selection decisions."""

    model_config = ConfigDict(extra="forbid")
    questions: list[_PlanningQuestionTransport] = Field(min_length=1, max_length=3)
    goalText: str
    observableResponse: str
    responseLevel: str
    scenarios: list[str]
    selectedMaterials: list[str]
    theme: str
    duration: str
    customNotes: str


class _ProfileLearnerTransport(BaseModel):
    """Compact provider boundary; compatibility fields are derived locally."""

    model_config = ConfigDict(extra="forbid")
    age: int = Field(ge=0, le=30)
    normalizedProfile: CanonicalLearnerProfile


class _ProfileExtractionTransport(BaseModel):
    """Avoid duplicating the canonical factors in the paid AI response."""

    model_config = ConfigDict(extra="forbid")
    learner: _ProfileLearnerTransport
    unknownFields: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)


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
                max_retries=self._settings.OPENAI_MAX_RETRIES,
            )
        return self._client

    def _request_client(self, timeout_seconds: int | None = None) -> Any:
        """Return a request-scoped client without mutating the shared client.

        Profile extraction has a tighter latency budget than lesson generation.
        Injected test clients intentionally do not need to implement with_options.
        """

        client = self._get_client()
        if timeout_seconds is not None and hasattr(client, "with_options"):
            return client.with_options(timeout=timeout_seconds)
        return client

    def _reasoning_options(self, model: str) -> dict[str, Any]:
        # GPT-4.1 models do not use the GPT-5 reasoning controls. Keeping this
        # conditional lets profile extraction use a fast non-reasoning model.
        if model.startswith("gpt-5"):
            return {
                "reasoning": {
                    "effort": self._settings.OPENAI_REASONING_EFFORT,
                }
            }
        return {}

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
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        # Resolve configuration before the vendor call so the deliberate, safe
        # missing-key error remains distinct from SDK/network failures.
        client = self._request_client(timeout_seconds)
        request_model = model or self._settings.OPENAI_TEXT_MODEL
        reasoning_options = self._reasoning_options(request_model)
        used_typed_parse = False
        try:
            if response_model is not None and hasattr(client.responses, "parse"):
                used_typed_parse = True
                try:
                    response = client.responses.parse(
                        model=request_model,
                        instructions=prompt.system_instructions,
                        input=prompt.user_input,
                        text_format=response_model,
                        **reasoning_options,
                    )
                except Exception as exc:
                    # Some otherwise supported models reject a particular strict
                    # JSON schema before generating tokens. Retry exactly once in
                    # JSON-object mode, then apply the same Pydantic validation
                    # below. Authentication, rate-limit, timeout, and server
                    # failures remain fail-closed and are not retried here.
                    if getattr(exc, "status_code", None) != 400:
                        raise
                    logger.warning(
                        "Structured output schema rejected; retrying JSON mode",
                        extra={
                            "event": "structured_output_retry",
                            "error_code": "structured_output_schema_rejected",
                        },
                    )
                    used_typed_parse = False
                    response = client.responses.create(
                        model=request_model,
                        instructions=prompt.system_instructions,
                        input=prompt.user_input,
                        text={"format": {"type": "json_object"}},
                        **reasoning_options,
                    )
            else:
                response = client.responses.create(
                    model=request_model,
                    instructions=prompt.system_instructions,
                    input=prompt.user_input,
                    text={"format": {"type": "json_object"}},
                    **reasoning_options,
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
        if response_model is not None and used_typed_parse:
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
        decoded = self._decode_json(content)
        if response_model is not None:
            try:
                return response_model.model_validate(decoded).model_dump(
                    mode="json", by_alias=True
                )
            except ValidationError as exc:
                raise _OpenAIOutputError(
                    "The model response did not match the required schema"
                ) from exc
        return decoded

    def _mark_fallback(
        self,
        operation: str,
        skill_id: str,
        failure_kind: str,
        model: str | None = None,
    ) -> None:
        self.last_fallback_used = True
        self._record_generation(
            self._registry,
            skill_id,
            status="local_mock",
            model=model or self._settings.OPENAI_TEXT_MODEL,
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
        self,
        operation: str,
        skill_id: str,
        failure_kind: str,
        model: str | None = None,
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
        self._mark_fallback(operation, skill_id, failure_kind, model)

    def _success(self, skill_id: str, model: str | None = None) -> None:
        self._record_generation(
            self._registry,
            skill_id,
            status="ready",
            model=model or self._settings.OPENAI_TEXT_MODEL,
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
    def _validate_lesson_questions(
        questions: list[AIQuestion], draft: LessonDesignDraft
    ) -> None:
        if not questions:
            raise _OpenAIOutputError("The lesson planner returned no questions")
        if not draft.goal_text.strip():
            raise _OpenAIOutputError("The lesson planner returned no draft goal")
        if len({question.id for question in questions}) != len(questions):
            raise _OpenAIOutputError("Lesson question IDs must be unique")
        for question in questions:
            if (
                question.input_type in {"single_select", "multi_select"}
                and not question.options
                and not question.allow_custom_answer
            ):
                raise _OpenAIOutputError(
                    "A selection question did not include any answer options"
                )

    @staticmethod
    def _planning_transport_to_domain(
        planning: _LessonPlanningTransport,
        learner: LearnerProfile,
        teacher_request: str,
        snapshot: InstructionalConstraintSnapshot,
        supported_material_catalog: list[str],
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        active_factor_ids = set(snapshot.profile_factor_ids)
        supported_keys = {item.strip().casefold() for item in supported_material_catalog}
        questions: list[AIQuestion] = []
        affects = {
            "goalText": ["lesson", "teaching_flow", "data_sheet", "materials"],
            "scenarios": ["lesson", "scenario_cards", "generalization_plan"],
            "selectedMaterials": ["materials", "printable_package"],
        }
        decision_fields = {
            "goalText": "goal",
            "scenarios": "practice_contexts",
            "selectedMaterials": "material_requests",
        }
        profile_contexts = list(
            dict.fromkeys(snapshot.generalization.contexts)
        )[:3]
        for item in planning.questions:
            options: list[AIQuestionOption] = []
            provider_options = item.options
            if item.field == "scenarios" and profile_contexts:
                options = [
                    AIQuestionOption(
                        id=f"profile-context-{index + 1}",
                        label=context,
                        value=context,
                        description=(
                            "Profile-confirmed classroom activity or transition."
                        ),
                        recommended=True,
                        source="ai_generated",
                        decisionField="practice_contexts",
                        reason=(
                            "Uses a reviewed learner-profile context instead of "
                            "inventing a generic setting."
                        ),
                        profileFactorIds=list(snapshot.profile_factor_ids),
                        affects=affects["scenarios"],
                        assumptions=[],
                        suggestionStatus="recommended",
                    )
                    for index, context in enumerate(profile_contexts)
                ]
                provider_options = []
            for option in provider_options:
                supported = True
                unsupported_reason = None
                if item.field == "selectedMaterials":
                    material_key = option.value.strip().casefold()
                    supported = material_key in supported_keys
                    if not supported:
                        unsupported_reason = (
                            "This provider material is outside the supported catalog and will not be remapped."
                        )
                options.append(
                    AIQuestionOption(
                        id=option.id,
                        label=option.label,
                        value=option.value,
                        description=option.description,
                        recommended=option.recommended,
                        source="ai_generated",
                        decisionField=decision_fields[item.field],
                        reason=option.reason,
                        profileFactorIds=[
                            factor_id
                            for factor_id in option.profileFactorIds
                            if factor_id in active_factor_ids
                        ],
                        affects=affects[item.field],
                        assumptions=option.assumptions,
                        suggestionStatus=(
                            "recommended" if option.recommended else "optional"
                        ),
                        supported=supported,
                        unsupportedReason=unsupported_reason,
                    )
                )
            questions.append(
                AIQuestion(
                    id=item.id,
                    prompt=item.prompt,
                    helperText=item.helperText,
                    field=item.field,
                    inputType=item.inputType,
                    options=options,
                    selectedOptionIds=[],
                    allowCustomAnswer=item.allowCustomAnswer,
                    required=True,
                    maxSelections=item.maxSelections,
                )
            )
        draft = LessonDesignDraft(
            id=f"ai-draft-{uuid4()}",
            learnerId=learner.id,
            goalText=planning.goalText,
            observableResponse=planning.observableResponse,
            responseLevel=planning.responseLevel,
            scenarios=profile_contexts or planning.scenarios[:3],
            selectedMaterials=planning.selectedMaterials,
            theme=planning.theme,
            duration=planning.duration,
            customNotes=planning.customNotes,
            teacherRequest=teacher_request,
            profileRevision=snapshot.profile_revision,
            instructionalConstraintSnapshot=snapshot,
        )
        return questions, draft

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
                        "learner": "verified age plus one complete normalizedProfile canonical profile",
                        "unknownFields": "array of field names",
                        "insights": "array of short strings",
                    },
                    trusted_input={"learner": payload["learner"]},
                    untrusted_input={"records": payload["records"]},
                ),
                _ProfileExtractionTransport,
                model=self._settings.OPENAI_PROFILE_MODEL,
                timeout_seconds=self._settings.OPENAI_PROFILE_TIMEOUT_SECONDS,
            )
            extracted_values = result["learner"]
            if not isinstance(extracted_values, dict):
                raise _OpenAIOutputError("Learner extraction must be an object")
            preserved = learner.model_dump()
            preserved.update(extracted_values)
            preserved["id"] = learner.id
            preserved["code"] = learner.code
            extracted = canonicalize_profile(LearnerProfile.model_validate(preserved))
            if (
                extracted.normalized_profile is None
                or not extracted.normalized_profile.factors
            ):
                raise _OpenAIOutputError(
                    "Learner extraction returned no structured profile factors"
                )
            insights = result["insights"]
            if not isinstance(insights, list) or not all(
                isinstance(item, str) for item in insights
            ):
                raise _OpenAIOutputError("Insights must be a list of strings")
            # Canonical profile factors are the single source of truth. Legacy
            # compatibility fields (including profileSignals) are projected
            # deterministically instead of asking the model to repeat evidence.
            signals = []
            unknown_fields = result.get("unknownFields", [])
            if not isinstance(unknown_fields, list) or not all(
                isinstance(item, str) for item in unknown_fields
            ):
                raise _OpenAIOutputError("unknownFields must be a list of strings")
            extracted.profile_signals = signals
            extracted.unknown_fields = unknown_fields
            self._success("learner_profile", self._settings.OPENAI_PROFILE_MODEL)
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
            failure_kind = self._failure_kind(exc)
            logger.warning(
                "Profile extraction failed validation",
                extra={"event": failure_kind, "error_code": failure_kind},
            )
            if failure_kind == "invalid_output":
                raise AIInvalidOutputError(
                    "The learner profile could not be validated. The reviewed record text is preserved; please retry extraction."
                ) from exc
            raise AIProviderFailureError(
                "Learner profile extraction is temporarily unavailable. The reviewed record text is preserved; please retry."
            ) from exc

    def generate_lesson_questions(
        self, learner: LearnerProfile, teacher_request: str
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        from app.services.v2_instructional_constraint_service import (
            build_instructional_constraint_snapshot,
        )

        return self.generate_lesson_questions_with_snapshot(
            learner,
            teacher_request,
            build_instructional_constraint_snapshot(learner, []),
            [],
        )

    def generate_lesson_questions_with_snapshot(
        self,
        learner: LearnerProfile,
        teacher_request: str,
        snapshot: InstructionalConstraintSnapshot,
        supported_material_catalog: list[str],
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        self.last_fallback_used = False
        try:
            skill = self._registry.get("lesson_planning")
            ny_material_skill = self._registry.get("ny_instructional_materials")
            result = self._request_json(
                self._prompts.build(
                    skill,
                    output_contract={
                        "questions": "one goal, one practice-context, and one printable-material question; each with 2-3 compact options",
                        "goalText": "observable suggested goal",
                        "observableResponse": "visible or countable response",
                        "responseLevel": "accepted response modes",
                        "scenarios": "up to three familiar practice contexts",
                        "selectedMaterials": "recommended names from supportedMaterialCatalog only",
                        "theme": "age-respectful personalization theme",
                        "duration": "brief suggested duration",
                        "customNotes": "concise access and safety reminders",
                    },
                    trusted_input={
                        "instructionalConstraintSnapshot": snapshot.model_dump(
                            mode="json", by_alias=True
                        ),
                        "profileRevision": snapshot.profile_revision,
                        "unresolvedAssumptions": snapshot.unresolved_assumptions,
                        "excludedItems": snapshot.excluded_items,
                        "supportedMaterialCatalog": supported_material_catalog,
                    },
                    untrusted_input={"teacherRequest": teacher_request},
                    supplemental_skills=(ny_material_skill,),
                ),
                _LessonPlanningTransport,
                model=self._settings.OPENAI_PLANNING_MODEL,
                timeout_seconds=self._settings.OPENAI_PLANNING_TIMEOUT_SECONDS,
            )
            planning = _LessonPlanningTransport.model_validate(result)
            questions, draft = self._planning_transport_to_domain(
                planning,
                learner,
                teacher_request,
                snapshot,
                supported_material_catalog,
            )
            self._validate_lesson_questions(questions, draft)
            self._success("lesson_planning", self._settings.OPENAI_PLANNING_MODEL)
            return questions, draft
        except (
            _OpenAIOutputError,
            _OpenAIRequestError,
            ValidationError,
            KeyError,
            TypeError,
        ) as exc:
            self._handle_provider_failure(
                "lesson question generation",
                "lesson_planning",
                self._failure_kind(exc),
                self._settings.OPENAI_PLANNING_MODEL,
            )
            questions, draft = self._fallback.generate_lesson_questions_with_snapshot(
                learner, teacher_request, snapshot, supported_material_catalog
            )
            draft.profile_revision = snapshot.profile_revision
            draft.instructional_constraint_snapshot = snapshot
            return questions, draft

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
        lesson_spec: LessonSpec,
    ) -> dict[str, Any]:
        lesson_spec = self._require_lesson_spec(lesson_spec)
        self.last_fallback_used = False
        try:
            lesson_skill = self._registry.get("lesson_generation")
            ny_material_skill = self._registry.get("ny_instructional_materials")
            prompt = self._prompts.build(
                lesson_skill,
                output_contract={
                    "lessonBrief": (
                        "concise personalized teacher brief grounded only in the "
                        "LessonSpec; no placeholders or unsupported claims"
                    ),
                    "summaryTemplate": (
                        "goal-specific closeout reminder using observable language"
                    ),
                    "teachingFlow": (
                        "3-6 complete classroom steps with compact scripts, exact "
                        "wait/prompt/data actions, neutral correction, and break access. "
                        "The success-criterion opportunity total is a budget for the "
                        "whole lesson; allocate it once across steps and never repeat "
                        "that full count in multiple steps"
                    ),
                },
                trusted_input={
                    "lessonSpec": lesson_spec.model_dump(mode="json", by_alias=True),
                },
                supplemental_skills=(ny_material_skill,),
            )
            result = self._request_json(
                prompt,
                _LessonPackageCopyTransport,
                model=self._settings.OPENAI_PACKAGE_MODEL,
                timeout_seconds=self._settings.OPENAI_PACKAGE_TIMEOUT_SECONDS,
            )
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
                "teachingFlow": self._normalize_opportunity_budget(
                    lesson_spec, result["teachingFlow"]
                ),
            }
            # The approved LessonSpec and PackageContentPlan already determine the
            # exact artifact inventory. Reuse the deterministic typed projection
            # instead of asking a model to author arbitrary nested material JSON.
            # This preserves personalization in the lesson copy while preventing
            # selected materials, counts, safety constraints, and revision lineage
            # from drifting at the provider boundary.
            generated["materials"] = [
                {
                    "type": request.material_type,
                    "title": request.display_label,
                    "content": {},
                }
                for request in lesson_spec.material_requests
                if request.required and request.supported
            ]
            self._success("lesson_generation", self._settings.OPENAI_PACKAGE_MODEL)
            self._record_generation(
                self._registry,
                "material_generation",
                status="ready",
                model=self._settings.OPENAI_PACKAGE_MODEL,
                output_source="provider",
                set_last=False,
            )
            return generated
        except (_OpenAIOutputError, _OpenAIRequestError, KeyError, TypeError) as exc:
            self._handle_provider_failure(
                "lesson package generation",
                "lesson_generation",
                self._failure_kind(exc),
                self._settings.OPENAI_PACKAGE_MODEL,
            )
            return self._fallback.generate_lesson_package(lesson_spec)

    @staticmethod
    def _normalize_opportunity_budget(
        lesson_spec: LessonSpec, teaching_flow: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Prevent provider copy from multiplying the LessonSpec trial budget.

        The model may correctly mention the total in one practice step and then
        repeat the same total in a later generalization step. That changes a
        five-opportunity lesson into ten teacher data entries. Keep the first
        exact allocation and describe later occurrences as the remaining
        opportunities without changing any teacher-authored LessonSpec value.
        """

        goal = getattr(lesson_spec, "goal", None)
        criterion = getattr(goal, "success_criterion", None)
        total = getattr(criterion, "total_opportunities", None)
        if not isinstance(total, int) or total < 1:
            return teaching_flow
        words = {
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
            10: "ten",
        }
        variants = [str(total)]
        if total in words:
            variants.append(words[total])
        pattern = re.compile(
            rf"\b(?:{'|'.join(re.escape(item) for item in variants)})\s+opportunit(?:y|ies)\b",
            re.IGNORECASE,
        )
        exact_allocation_seen = False
        normalized: list[dict[str, Any]] = []
        for step in teaching_flow:
            candidate = dict(step)
            for field in ("description", "teacherAction", "teacherScript"):
                value = candidate.get(field)
                if not isinstance(value, str):
                    continue

                def replace(match: re.Match[str]) -> str:
                    nonlocal exact_allocation_seen
                    if not exact_allocation_seen:
                        exact_allocation_seen = True
                        return match.group(0)
                    return "the remaining planned opportunities"

                candidate[field] = pattern.sub(replace, value)
            normalized.append(candidate)
        return normalized

    def revise_lesson_section(
        self,
        *,
        section_label: str,
        current_text: str,
        instruction: str,
        lesson_context: dict[str, Any],
    ) -> str:
        self.last_fallback_used = False
        try:
            skill = self._registry.get("lesson_generation")
            ny_material_skill = self._registry.get("ny_instructional_materials")
            result = self._request_json(
                self._prompts.build(
                    skill,
                    output_contract={
                        "revisedText": (
                            "the complete replacement text for only the selected "
                            "section; no markdown and no commentary"
                        )
                    },
                    trusted_input={
                        "sectionLabel": section_label,
                        "lessonContext": lesson_context,
                    },
                    untrusted_input={
                        "currentSectionText": current_text,
                        "teacherEditInstruction": instruction,
                    },
                    supplemental_skills=(ny_material_skill,),
                ),
                _LessonSectionRevision,
                model=self._settings.OPENAI_PACKAGE_MODEL,
                timeout_seconds=self._settings.OPENAI_PACKAGE_TIMEOUT_SECONDS,
            )
            revised = str(result.get("revisedText") or "").strip()
            if not revised:
                raise _OpenAIOutputError("The section revision was empty")
            self._success("lesson_generation", self._settings.OPENAI_PACKAGE_MODEL)
            return revised
        except (
            _OpenAIOutputError,
            _OpenAIRequestError,
            ValidationError,
            KeyError,
            TypeError,
        ) as exc:
            self._handle_provider_failure(
                "lesson section revision",
                "lesson_generation",
                self._failure_kind(exc),
                self._settings.OPENAI_PACKAGE_MODEL,
            )
            return self._fallback.revise_lesson_section(
                section_label=section_label,
                current_text=current_text,
                instruction=instruction,
                lesson_context=lesson_context,
            )

    def repair_material_spec(
        self,
        material_spec: MaterialSpec,
        issues: list[MaterialValidationIssue],
        lesson_spec: LessonSpec,
    ) -> MaterialSpec:
        skill = self._registry.get("material_generation")
        result = self._request_json(
            self._prompts.build(
                skill,
                output_contract={
                    "materialSpec": (
                        "the complete repaired MaterialSpec using the identical "
                        "artifact type and protected LessonSpec constraints"
                    )
                },
                trusted_input={
                    "existingMaterialSpec": material_spec.model_dump(mode="json", by_alias=True),
                    "validationIssues": [item.model_dump(mode="json", by_alias=True) for item in issues],
                    "protectedLessonSpec": lesson_spec.model_dump(mode="json", by_alias=True),
                },
            ),
            type(material_spec),
            model=self._settings.OPENAI_PACKAGE_MODEL,
            timeout_seconds=self._settings.OPENAI_PACKAGE_TIMEOUT_SECONDS,
        )
        return type(material_spec).model_validate(result)

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
                    quality="low",
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
