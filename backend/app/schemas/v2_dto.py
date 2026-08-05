from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class V2Model(BaseModel):
    """Base contract for v2: Python internals stay idiomatic, JSON stays camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class HealthResponse(V2Model):
    status: Literal["ok"] = "ok"
    version: str = "v2-product"
    environment: Literal["development", "test", "staging", "production"] = "development"


class AuthenticatedTeacherDto(V2Model):
    subject: str
    display_name: str
    email: str | None = None
    organization_id: str
    role: Literal["viewer", "teacher", "admin"]
    expires_at: int | None = None
    authentication_mode: Literal["demo", "cognito"]


GenerationStatus = Literal[
    "ready", "provider_failure", "invalid_output", "retry_required", "local_mock"
]


class GenerationMetadataDto(V2Model):
    status: GenerationStatus
    provider: str
    model: str
    skillId: str
    skillVersion: str
    promptTemplateVersion: str
    inputSchemaVersion: str
    outputSchemaVersion: str
    evaluatorVersion: str
    generatedAt: str
    outputSource: Literal["provider", "local_mock", "mock_fallback"]
    teacherReviewRequired: bool


ProfileSignalCategory = Literal[
    "interest",
    "reinforcer",
    "communication",
    "support_need",
    "sensory_preference",
    "strength",
    "challenge",
    "prompting",
    "goal",
    "response_option",
    "receptive_support",
    "expressive_support",
    "attention_engagement",
    "environment",
    "effective_support",
    "ineffective_support",
    "independence",
    "mastered_skill",
    "emerging_skill",
    "generalization",
    "break_preference",
    "classroom_barrier",
]
ProfileSignalStatus = Literal["suggested", "confirmed", "rejected"]
ProfileReviewStatus = Literal["draft", "reviewed", "confirmed"]
EvidenceType = Literal[
    "documented_fact",
    "teacher_report",
    "caregiver_report",
    "observation",
    "interpretation",
    "contradiction",
    "outdated_evidence",
    "unknown",
]


class ProfileSignal(V2Model):
    id: str
    category: ProfileSignalCategory
    label: str
    confidence: float = Field(ge=0, le=1)
    status: ProfileSignalStatus = "suggested"
    evidence: str = ""
    source_record_id: str | None = None
    summary: str = ""
    evidence_type: EvidenceType = "documented_fact"
    source_location: str | None = None
    evidence_date: str | None = None
    contradiction_state: Literal["none", "conflicting", "resolved", "outdated"] = "none"
    suggested_profile_value: str = ""
    teacher_review_state: Literal[
        "pending", "confirmed", "edited", "rejected", "unknown"
    ] = "pending"
    evidence_fingerprint: str = ""


ProfileFactorCategory = Literal[
    "communication",
    "receptive_language",
    "learning_strength",
    "attention",
    "sensory",
    "visual_access",
    "motor_access",
    "current_interest",
    "historical_interest",
    "reinforcement",
    "transition",
    "regulation",
    "prompting",
    "error_correction",
    "generalization",
    "language",
    "safety",
    "prohibited_item",
    "unresolved_assumption",
    "other",
]
ProfileFactorStatus = Literal[
    "confirmed_current",
    "teacher_confirmed",
    "teacher_edited",
    "historical",
    "unconfirmed",
    "not_approved",
    "not_meaningful",
    "omitted",
    "derived",
    "rejected",
]


class ProfileFactor(V2Model):
    """One evidence-linked, actionable learner-profile fact."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: ProfileFactorCategory
    label: str
    value: str
    status: ProfileFactorStatus
    confidence: float = Field(ge=0, le=1)
    source_evidence: str
    source_record_id: str | None = None
    instructional_implication: str
    generation_constraints: list[str] = Field(default_factory=list)
    teacher_reviewed: bool = False


class LearnerProfileSummary(V2Model):
    model_config = ConfigDict(extra="forbid")
    communication: str = ""
    supports: list[str] = Field(default_factory=list)
    current_interests: list[str] = Field(default_factory=list)
    learning_format: str = ""
    key_teaching_notes: list[str] = Field(default_factory=list)


class CanonicalLearnerProfile(V2Model):
    model_config = ConfigDict(extra="forbid")
    learner_id: str
    age: int
    factors: list[ProfileFactor] = Field(default_factory=list)
    confirmed_factor_ids: list[str] = Field(default_factory=list)
    unconfirmed_factor_ids: list[str] = Field(default_factory=list)
    historical_factor_ids: list[str] = Field(default_factory=list)
    excluded_factor_ids: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    summary: LearnerProfileSummary = Field(default_factory=LearnerProfileSummary)


class CommunicationConstraints(V2Model):
    accepted_modes: list[str] = Field(default_factory=list)
    response_options: list[str] = Field(default_factory=list)
    processing_time_seconds: int | None = None
    access_requirements: list[str] = Field(default_factory=list)
    invalid_requirements: list[str] = Field(default_factory=list)


class InstructionConstraints(V2Model):
    effective_supports: list[str] = Field(default_factory=list)
    ineffective_supports: list[str] = Field(default_factory=list)
    prompt_hierarchy: list[str] = Field(default_factory=list)
    prohibited_prompting: list[str] = Field(default_factory=list)
    error_correction: list[str] = Field(default_factory=list)
    activity_duration_minutes: int | None = None
    visible_endpoint_required: bool = False


class VisualAndSensoryAccessConstraints(V2Model):
    maximum_primary_choices: int | None = None
    layout_requirements: list[str] = Field(default_factory=list)
    preferred_organizing_features: list[str] = Field(default_factory=list)
    prohibited_visual_features: list[str] = Field(default_factory=list)
    prohibited_audio_features: list[str] = Field(default_factory=list)
    motor_access_alternatives: list[str] = Field(default_factory=list)


class EngagementConstraints(V2Model):
    current_interests: list[str] = Field(default_factory=list)
    historical_interests: list[str] = Field(default_factory=list)
    effective_reinforcers: list[str] = Field(default_factory=list)
    not_approved_reinforcers: list[str] = Field(default_factory=list)
    not_meaningful_reinforcers: list[str] = Field(default_factory=list)


class TransitionAndBreakConstraints(V2Model):
    difficult_transitions: list[str] = Field(default_factory=list)
    transition_warnings: list[str] = Field(default_factory=list)
    first_then_required: bool = False
    break_request_options: list[str] = Field(default_factory=list)
    break_duration_minutes: int | None = None
    return_supports: list[str] = Field(default_factory=list)


class GeneralizationConstraints(V2Model):
    required: bool = False
    contexts: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)


class InstructionalConstraintSnapshot(V2Model):
    learner_id: str
    profile_revision: str
    generated_at: datetime = Field(default_factory=utc_now)
    communication: CommunicationConstraints = Field(
        default_factory=CommunicationConstraints
    )
    instruction: InstructionConstraints = Field(default_factory=InstructionConstraints)
    visual_and_sensory_access: VisualAndSensoryAccessConstraints = Field(
        default_factory=VisualAndSensoryAccessConstraints
    )
    engagement: EngagementConstraints = Field(default_factory=EngagementConstraints)
    transitions_and_breaks: TransitionAndBreakConstraints = Field(
        default_factory=TransitionAndBreakConstraints
    )
    generalization: GeneralizationConstraints = Field(
        default_factory=GeneralizationConstraints
    )
    safety_constraints: list[str] = Field(default_factory=list)
    unresolved_assumptions: list[str] = Field(default_factory=list)
    excluded_items: list[str] = Field(default_factory=list)
    profile_factor_ids: list[str] = Field(default_factory=list)


class LearnerProfile(V2Model):
    model_config = ConfigDict(extra="forbid")
    id: str
    code: str
    age: int
    avatar: str = ""
    tags: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    support_needs: list[str] = Field(default_factory=list)
    reinforcement_preferences: list[str] = Field(default_factory=list)
    communication_mode: str = ""
    attention_profile: str = ""
    notes: str = ""
    strengths: list[str] = Field(default_factory=list)
    sensory_preferences: list[str] = Field(default_factory=list)
    known_challenges: list[str] = Field(default_factory=list)
    prompting_preferences: list[str] = Field(default_factory=list)
    current_goals: list[str] = Field(default_factory=list)
    reading_level: str = ""
    activity_duration_preference: str = ""
    response_options: list[str] = Field(default_factory=list)
    receptive_supports: list[str] = Field(default_factory=list)
    expressive_supports: list[str] = Field(default_factory=list)
    environmental_considerations: list[str] = Field(default_factory=list)
    effective_supports: list[str] = Field(default_factory=list)
    ineffective_supports: list[str] = Field(default_factory=list)
    independence_profile: str = ""
    mastered_skills: list[str] = Field(default_factory=list)
    emerging_skills: list[str] = Field(default_factory=list)
    generalization_profile: str = ""
    break_preferences: list[str] = Field(default_factory=list)
    classroom_barriers: list[str] = Field(default_factory=list)
    normalized_profile: CanonicalLearnerProfile | None = None
    profile_signals: list[ProfileSignal] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    profile_review_status: ProfileReviewStatus = "draft"
    version: int = 1


class LearnerCreate(V2Model):
    code: str
    age: int
    tags: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    support_needs: list[str] = Field(default_factory=list)
    reinforcement_preferences: list[str] = Field(default_factory=list)
    communication_mode: str = ""
    attention_profile: str = ""
    notes: str = ""
    strengths: list[str] = Field(default_factory=list)
    sensory_preferences: list[str] = Field(default_factory=list)
    known_challenges: list[str] = Field(default_factory=list)
    prompting_preferences: list[str] = Field(default_factory=list)
    current_goals: list[str] = Field(default_factory=list)
    reading_level: str = ""
    activity_duration_preference: str = ""
    response_options: list[str] = Field(default_factory=list)
    receptive_supports: list[str] = Field(default_factory=list)
    expressive_supports: list[str] = Field(default_factory=list)
    environmental_considerations: list[str] = Field(default_factory=list)
    effective_supports: list[str] = Field(default_factory=list)
    ineffective_supports: list[str] = Field(default_factory=list)
    independence_profile: str = ""
    mastered_skills: list[str] = Field(default_factory=list)
    emerging_skills: list[str] = Field(default_factory=list)
    generalization_profile: str = ""
    break_preferences: list[str] = Field(default_factory=list)
    classroom_barriers: list[str] = Field(default_factory=list)
    normalized_profile: CanonicalLearnerProfile | None = None
    profile_signals: list[ProfileSignal] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    profile_review_status: ProfileReviewStatus = "draft"


class LearnerUpdate(V2Model):
    code: str | None = None
    age: int | None = None
    tags: list[str] | None = None
    interests: list[str] | None = None
    support_needs: list[str] | None = None
    reinforcement_preferences: list[str] | None = None
    communication_mode: str | None = None
    attention_profile: str | None = None
    notes: str | None = None
    strengths: list[str] | None = None
    sensory_preferences: list[str] | None = None
    known_challenges: list[str] | None = None
    prompting_preferences: list[str] | None = None
    current_goals: list[str] | None = None
    reading_level: str | None = None
    activity_duration_preference: str | None = None
    response_options: list[str] | None = None
    receptive_supports: list[str] | None = None
    expressive_supports: list[str] | None = None
    environmental_considerations: list[str] | None = None
    effective_supports: list[str] | None = None
    ineffective_supports: list[str] | None = None
    independence_profile: str | None = None
    mastered_skills: list[str] | None = None
    emerging_skills: list[str] | None = None
    generalization_profile: str | None = None
    break_preferences: list[str] | None = None
    classroom_barriers: list[str] | None = None
    normalized_profile: CanonicalLearnerProfile | None = None
    profile_signals: list[ProfileSignal] | None = None
    unknown_fields: list[str] | None = None
    profile_review_status: ProfileReviewStatus | None = None
    expected_version: int | None = Field(default=None, ge=1)


class ProfileSignalReviewRequest(V2Model):
    decision: Literal["confirm", "edit", "reject", "leave_unknown"]
    editedValue: str | None = Field(default=None, max_length=1000)
    expectedVersion: int = Field(ge=1)


class ProfileFactorReviewRequest(V2Model):
    decision: Literal["confirm", "edit", "reject"]
    edited_value: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=1)


class ProfileConfirmRequest(V2Model):
    expectedVersion: int = Field(ge=1)


RecordStatus = Literal[
    "upload_pending",
    "uploaded",
    "validating",
    "parsing",
    "needs_ocr",
    "needs_review",
    "ready",
    "reviewed",
    "failed",
    "deleted",
    "processing",
]


class LearnerRecord(V2Model):
    id: str
    learner_id: str
    file_name: str
    file_type: str
    status: RecordStatus
    uploaded_at: datetime
    extracted_text: str = ""
    teacher_corrected_text: str | None = None
    storage_key: str | None = None
    declared_content_type: str = "application/octet-stream"
    expected_size_bytes: int = 0
    object_size_bytes: int | None = None
    malware_scan_status: Literal[
        "not_configured", "pending", "clean", "blocked", "failed"
    ] = "not_configured"
    parsing_message: str = ""
    extraction_method: str = "parser"
    deletion_status: Literal["active", "pending", "failed", "deleted"] = "active"
    upload_completed_at: datetime | None = None
    version: int = 1

    @property
    def effective_text(self) -> str:
        return self.teacher_corrected_text or self.extracted_text


class RecordCreate(V2Model):
    file_name: str
    file_type: str
    pasted_text: str = ""


class RecordUploadRequest(V2Model):
    """JSON-only upload contract until multipart storage/parsing is introduced."""

    fileName: str
    fileType: str
    text: str = ""


class RecordUploadIntentRequest(V2Model):
    fileName: str
    contentType: str
    sizeBytes: int = Field(gt=0)


class RecordUploadIntentResponse(V2Model):
    record: "LearnerRecordDto"
    uploadUrl: str
    method: Literal["PUT"] = "PUT"
    requiredHeaders: dict[str, str] = Field(default_factory=dict)
    expiresAt: str


class RecordUploadCompleteRequest(V2Model):
    model_config = ConfigDict(extra="forbid")


class RecordTextCorrectionRequest(V2Model):
    correctedText: str = Field(min_length=1)
    expectedVersion: int | None = Field(default=None, ge=1)


class RecordDeletionResponse(V2Model):
    recordId: str
    status: Literal["deleted", "deletion_failed"]
    retryable: bool
    message: str


class ProfileExtraction(V2Model):
    learner: LearnerProfile
    records: list[LearnerRecord]
    insights: list[str]
    analyzed_record_count: int
    status: Literal["complete"] = "complete"


class ProfileExtractionResult(V2Model):
    """Provider result before records and persistence metadata are added."""

    model_config = ConfigDict(extra="forbid")

    learner: LearnerProfile
    profile_signals: list[ProfileSignal] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    generation_status: GenerationStatus | None = None
    generation_metadata: GenerationMetadataDto | None = None


class AIMessage(V2Model):
    id: str
    role: Literal["teacher", "assistant"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class AIQuestionOption(V2Model):
    id: str
    label: str
    value: str
    description: str = ""
    icon: str = ""
    recommended: bool = False
    source: Literal["ai_generated", "teacher_custom"] = "ai_generated"
    decision_field: Literal["goal", "practice_contexts", "material_requests"] | None = None
    reason: str = ""
    profile_factor_ids: list[str] = Field(default_factory=list)
    affects: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    suggestion_status: Literal[
        "recommended", "optional", "requires_confirmation", "blocked"
    ] = "optional"
    supported: bool = True
    unsupported_reason: str | None = None
    saved_for_future: bool = False


class GoalDecisionValue(V2Model):
    teacher_request: str = ""
    interpreted_goal: str = ""
    observable_behavior: str = ""
    conditions: str = ""
    success_criterion: str = ""
    accepted_response_modes: list[str] = Field(default_factory=list)
    baseline_assumptions: list[str] = Field(default_factory=list)


class PracticeContextItem(V2Model):
    id: str
    label: str
    setting: str = ""
    transition_from: str = ""
    transition_to: str = ""
    generalization_dimension: Literal["activity", "person", "setting", "material"] = "setting"


class PracticeContextDecisionValue(V2Model):
    contexts: list[PracticeContextItem] = Field(default_factory=list)


class MaterialRequestItem(V2Model):
    request_id: str
    material_type: str
    custom_label: str | None = None
    purpose: str = ""
    required: bool = True
    profile_factor_ids: list[str] = Field(default_factory=list)
    supported: bool = True
    unsupported_reason: str | None = None
    library_material_id: str | None = None
    library_material_version: int | None = None
    library_configuration: dict[str, Any] | None = None
    origin: Literal["newly_generated", "library_reused", "future_unsupported"] = "newly_generated"


class MaterialRequestDecisionValue(V2Model):
    materials: list[MaterialRequestItem] = Field(default_factory=list)


TeacherDecisionValue = GoalDecisionValue | PracticeContextDecisionValue | MaterialRequestDecisionValue


class TeacherDecision(V2Model):
    id: str
    field: Literal["goal", "practice_contexts", "material_requests"]
    source: Literal[
        "ai_recommended", "teacher_selected", "teacher_authored", "teacher_edited"
    ]
    option_ids: list[str] = Field(default_factory=list)
    profile_factor_ids: list[str] = Field(default_factory=list)
    value: TeacherDecisionValue
    reason: str = ""
    affects: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confirmed_at: datetime = Field(default_factory=utc_now)
    confirmed_by: Literal["teacher"] = "teacher"
    revision: int = 1


class StructuredTeacherChange(V2Model):
    id: str
    change_type: Literal[
        "goal_clarification", "context_change", "material_change", "duration_change",
        "reinforcement_change", "prompting_change", "general_note"
    ]
    original_message: str
    value: str
    created_at: datetime = Field(default_factory=utc_now)


LessonSpecValueSource = Literal[
    "teacher_authored", "teacher_selected", "ai_recommended",
    "profile_derived", "explicit_default", "legacy_adapter"
]


class LessonSpecFieldResolution(V2Model):
    field_path: str
    source: LessonSpecValueSource
    reason: str
    requires_teacher_confirmation: bool = False


class LessonSuccessCriterion(V2Model):
    required_successful_opportunities: int | None = Field(default=None, ge=1, le=50)
    total_opportunities: int | None = Field(default=None, ge=1, le=50)
    maximum_prompt_level: str = ""
    required_contexts: int = Field(default=1, ge=1, le=20)


class LessonSpecGoal(V2Model):
    display_text: str
    observable_behavior: str
    conditions: str = ""
    accepted_response_modes: list[str] = Field(default_factory=list)
    independence_definition: str = ""
    success_criterion: LessonSuccessCriterion | None = None


class LessonDurationSpec(V2Model):
    total_minutes: int = Field(ge=1, le=480)
    maximum_activity_block_minutes: int = Field(ge=1, le=120)


class LessonCommunicationPlan(V2Model):
    accepted_modes: list[str] = Field(default_factory=list)
    processing_time_seconds: int | None = Field(default=None, ge=0, le=120)
    response_validation_rules: list[str] = Field(default_factory=list)


class LessonPromptingPlan(V2Model):
    sequence: list[str] = Field(default_factory=list)
    prohibited_prompts: list[str] = Field(default_factory=list)
    fade_rule: str = ""
    wait_time_seconds: int | None = Field(default=None, ge=0, le=120)
    teacher_override: str = ""


class LessonErrorCorrectionSpec(V2Model):
    strategies: list[str] = Field(default_factory=list)


class LessonReinforcementPlan(V2Model):
    token_count: int | None = Field(default=None, ge=1, le=100)
    token_theme: str = ""
    earned_reward: str = ""
    reward_duration_minutes: int | None = Field(default=None, ge=1, le=120)
    specific_praise: str = ""
    excluded_reinforcers: list[str] = Field(default_factory=list)


class LessonTransitionPlan(V2Model):
    warning: str = ""
    first_then_required: bool = False
    break_request: str = ""
    break_duration_minutes: int | None = Field(default=None, ge=1, le=120)
    return_support: str = ""


class LessonAccessPlan(V2Model):
    maximum_primary_visual_choices: int | None = Field(default=None, ge=1, le=50)
    layout_requirements: list[str] = Field(default_factory=list)
    prohibited_visual_features: list[str] = Field(default_factory=list)
    prohibited_audio_features: list[str] = Field(default_factory=list)
    motor_access_alternatives: list[str] = Field(default_factory=list)


class LessonGeneralizationPlan(V2Model):
    required: bool = False
    contexts: list[PracticeContextItem] = Field(default_factory=list)
    dimensions: list[Literal["activity", "person", "setting", "material"]] = Field(default_factory=list)


class LessonDataPlan(V2Model):
    measures: list[str] = Field(default_factory=list)
    trial_definition: str = ""
    independence_definition: str = ""
    prompt_levels: list[str] = Field(default_factory=list)


class LessonMaterialConfigurationEntry(V2Model):
    key: str
    value: str | int | float | bool | None


class LessonSpecMaterialRequest(V2Model):
    request_id: str
    material_type: str
    display_label: str
    instructional_purpose: str
    required: bool = True
    supported: bool = True
    unsupported_reason: str | None = None
    profile_factor_ids: list[str] = Field(default_factory=list)
    origin: Literal["newly_generated", "library_reused", "future_unsupported"] = "newly_generated"
    library_material_id: str | None = None
    library_material_version: int | None = None
    configuration: list[LessonMaterialConfigurationEntry] = Field(default_factory=list)


class LessonSpecAssumption(V2Model):
    text: str
    blocking: bool = False
    profile_factor_id: str | None = None


class PackageCoreMaterial(V2Model):
    material_request_id: str
    material_type: str
    reason: str
    decision_ids: list[str] = Field(default_factory=list)
    profile_factor_ids: list[str] = Field(default_factory=list)


class PackageRequiredCompanion(V2Model):
    material_type: str
    reason_required: str
    depends_on_material_types: list[str] = Field(default_factory=list)
    goal_requirement: str
    profile_factor_ids: list[str] = Field(default_factory=list)
    can_teacher_remove: bool = False
    removal_warning: str | None = None
    included: bool = True


class PackageOptionalEnrichment(V2Model):
    material_type: str
    reason_suggested: str
    profile_factor_ids: list[str] = Field(default_factory=list)
    default_included: bool = True
    estimated_pages: int = Field(default=1, ge=1, le=20)


class PackageExcludedMaterial(V2Model):
    material_type: str
    reason_excluded: str
    profile_factor_ids: list[str] = Field(default_factory=list)


class PackageContentPlan(V2Model):
    id: str
    lesson_spec_id: str
    lesson_spec_revision: int = Field(ge=1)
    schema_version: Literal[1] = 1
    teacher_selected_core: list[PackageCoreMaterial] = Field(default_factory=list)
    required_companions: list[PackageRequiredCompanion] = Field(default_factory=list)
    optional_enrichments: list[PackageOptionalEnrichment] = Field(default_factory=list)
    excluded_materials: list[PackageExcludedMaterial] = Field(default_factory=list)
    estimated_artifact_count: int = Field(default=0, ge=0)
    estimated_page_count: int = Field(default=0, ge=0)
    unresolved_dependencies: list[str] = Field(default_factory=list)


class PackageContentPlanActionRequest(V2Model):
    action: Literal["set_optional", "set_companion", "add_material"]
    material_type: str
    included: bool = True
    expected_draft_version: int = Field(ge=1)


class LessonSpecProvenance(V2Model):
    teacher_authored_fields: list[str] = Field(default_factory=list)
    teacher_selected_fields: list[str] = Field(default_factory=list)
    ai_recommended_fields: list[str] = Field(default_factory=list)
    derived_fields: list[str] = Field(default_factory=list)
    defaulted_fields: list[str] = Field(default_factory=list)
    field_resolutions: list[LessonSpecFieldResolution] = Field(default_factory=list)


class LessonSpec(V2Model):
    id: str
    schema_version: Literal[1] = 1
    revision: int = Field(default=1, ge=1)
    learner_id: str
    profile_revision: str
    teacher_request: str
    teacher_edits: list[str] = Field(default_factory=list)
    goal: LessonSpecGoal
    duration: LessonDurationSpec
    contexts: list[PracticeContextItem] = Field(default_factory=list)
    communication_plan: LessonCommunicationPlan
    prompting_plan: LessonPromptingPlan
    error_correction_plan: LessonErrorCorrectionSpec = Field(default_factory=LessonErrorCorrectionSpec)
    reinforcement_plan: LessonReinforcementPlan
    transition_plan: LessonTransitionPlan
    access_plan: LessonAccessPlan
    generalization_plan: LessonGeneralizationPlan
    data_plan: LessonDataPlan
    material_requests: list[LessonSpecMaterialRequest] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    personalization_themes: list[str] = Field(default_factory=list)
    unresolved_assumptions: list[LessonSpecAssumption] = Field(default_factory=list)
    profile_factor_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    provenance: LessonSpecProvenance

    # Internal read-only projections keep existing deterministic material
    # builders operating on the canonical spec during the migration. They are
    # not serialized and do not create a second generation input contract.
    @property
    def goalText(self) -> str:
        return self.goal.display_text

    @property
    def observableResponse(self) -> str:
        return self.goal.observable_behavior

    @property
    def responseLevel(self) -> str:
        return ", ".join(self.goal.accepted_response_modes)

    @property
    def scenarios(self) -> list[str]:
        return [item.label for item in self.contexts]

    @property
    def selectedMaterials(self) -> list[str]:
        return [item.material_type for item in self.material_requests if item.required and item.supported]

    @property
    def theme(self) -> str:
        return self.personalization_themes[0] if self.personalization_themes else ""

    @property
    def promptingStart(self) -> str:
        return ", then ".join(self.prompting_plan.sequence)

    @property
    def promptingLimits(self) -> str:
        return "; ".join(
            value
            for value in (
                self.prompting_plan.teacher_override,
                *self.prompting_plan.prohibited_prompts,
            )
            if value.strip()
        )

    @property
    def reinforcementPlan(self) -> str:
        return self.reinforcement_plan.earned_reward or self.reinforcement_plan.specific_praise

    @property
    def customNotes(self) -> str:
        return "; ".join(self.teacher_edits)

    @property
    def errorCorrection(self) -> str:
        return "; ".join(self.error_correction_plan.strategies)

    @property
    def teacherConstraints(self) -> str:
        return "; ".join(self.safety_constraints)

    @property
    def opportunities(self) -> int:
        criterion = self.goal.success_criterion
        return criterion.total_opportunities if criterion and criterion.total_opportunities else 0

    @property
    def baseline(self) -> str:
        return "Teacher-confirmed baseline required"

    @property
    def dataCollection(self) -> str:
        return ", ".join(self.data_plan.measures)

    @property
    def generalizationPlan(self) -> str:
        return ", ".join(item.label for item in self.generalization_plan.contexts)


class LessonSpecValidationIssue(V2Model):
    field_path: str
    code: str
    message: str
    remediation: str


class LessonSpecValidationReport(V2Model):
    valid: bool
    issues: list[LessonSpecValidationIssue] = Field(default_factory=list)


class AIQuestion(V2Model):
    id: str
    prompt: str
    helper_text: str = ""
    field: Literal[
        "goalText",
        "baseline",
        "responseLevel",
        "scenarios",
        "opportunities",
        "duration",
        "promptingStart",
        "promptingLimits",
        "reinforcementPlan",
        "errorCorrection",
        "selectedMaterials",
        "dataCollection",
        "generalizationPlan",
        "teacherConstraints",
        "customNotes",
    ]
    input_type: Literal["single_select", "multi_select", "free_text", "hybrid"]
    options: list[AIQuestionOption] = Field(default_factory=list)
    selected_option_ids: list[str] = Field(default_factory=list)
    allow_custom_answer: bool = False
    custom_answer: str = ""
    required: bool = True
    max_selections: int | None = None


class LessonDesignDraft(V2Model):
    id: str
    learner_id: str
    goal_text: str = ""
    response_level: str = ""
    scenarios: list[str] = Field(default_factory=list)
    selected_materials: list[str] = Field(default_factory=list)
    theme: str = ""
    duration: str = ""
    custom_notes: str = ""
    baseline: str = "Unknown — teacher confirmation needed"
    observable_response: str = ""
    opportunities: int = Field(default=5, ge=1, le=50)
    prompting_start: str = "Wait, then use least-to-most support"
    prompting_limits: str = "Teacher may pause or change prompting at any time"
    reinforcement_plan: str = "Specific praise and learner choice"
    error_correction: str = "Neutral feedback, model, and another opportunity"
    data_collection: str = "Record independence, prompt level, and response outcome"
    generalization_plan: str = "Practice across examples, people, and settings"
    teacher_constraints: str = ""
    profile_revision: str = ""
    instructional_constraint_snapshot: InstructionalConstraintSnapshot | None = None
    profile_stale: bool = False
    profile_stale_message: str = ""
    teacher_request: str = ""
    decisions: list[TeacherDecision] = Field(default_factory=list)
    structured_changes: list[StructuredTeacherChange] = Field(default_factory=list)
    supplemental_suggestions: list[AIQuestion] = Field(default_factory=list)
    package_content_plan: PackageContentPlan | None = None
    version: int = 1


class LessonPlanningResult(V2Model):
    """Typed provider contract for dynamic lesson questions and their draft."""

    questions: list[AIQuestion] = Field(min_length=1)
    draft: LessonDesignDraft


class AIChatState(V2Model):
    conversation_id: str
    learner_id: str
    messages: list[AIMessage] = Field(default_factory=list)
    questions: list[AIQuestion] = Field(default_factory=list)
    draft: LessonDesignDraft
    can_generate: bool = False
    generation_status: GenerationStatus | None = None
    generation_metadata: GenerationMetadataDto | None = None


class LessonChatRequest(V2Model):
    learner_id: str


class LessonRequestSubmit(V2Model):
    content: str = Field(min_length=1, max_length=4000)


class QuestionAnswerUpdate(V2Model):
    selected_option_ids: list[str] = Field(default_factory=list)
    custom_answer: str = ""
    expected_draft_version: int | None = Field(default=None, ge=1)
    save_unsupported_for_future: bool = False


class TeachingStep(V2Model):
    id: str
    title: str
    description: str
    duration: str
    teacher_action: str
    learner_action: str


class PrintLayout(V2Model):
    page_size: Literal["Letter", "A4"] = "Letter"
    orientation: Literal["portrait", "landscape"] = "portrait"
    color: str = "blue"


MaterialStatus = Literal["ready", "approved"]
GeneratedMaterialType = Literal[
    "blue_line_activity",
    "visual_timer",
    "quantity_cards",
    "number_cards",
    "visual_card",
    "choice_board",
    "first_then_board",
    "help_card",
    "break_card",
    "token_board",
    "sorting_page",
    "matching_page",
    "scenario_cards",
    "sequence_cards",
    "social_narrative",
    "core_word_board",
    "visual_schedule",
    "task_analysis_cards",
    "emotion_scale",
    "teacher_cue_card",
    "data_sheet",
    "session_summary",
    "summary_template",
    "handoff_note",
]


class GeneratedMaterial(V2Model):
    id: str
    package_id: str
    type: GeneratedMaterialType
    title: str
    status: MaterialStatus = "ready"
    content: dict[str, Any] = Field(default_factory=dict)
    print_layout: PrintLayout = Field(default_factory=PrintLayout)
    version: int = 1


class CheckResult(V2Model):
    id: str
    category: str
    passed: bool
    severity: Literal["info", "warning", "blocking"] = "info"
    message: str


class SafetyReport(V2Model):
    passed: bool
    checks: list[CheckResult]
    reviewed_at: datetime = Field(default_factory=utc_now)


class StandardsReport(V2Model):
    jurisdiction: str
    framework: str
    checks: list[CheckResult]


class LessonPackage(V2Model):
    id: str
    learner_id: str
    draft_id: str
    goal: str
    duration: str
    theme: str
    lesson_brief: str
    teaching_flow: list[TeachingStep]
    materials: list[GeneratedMaterial]
    summary_template: str
    safety_report: SafetyReport
    standards_report: StandardsReport
    created_at: datetime = Field(default_factory=utc_now)
    version: int = 1


class MaterialUpdate(V2Model):
    title: str | None = None
    status: MaterialStatus | None = None
    content: dict[str, Any] | None = None
    print_layout: PrintLayout | None = None


class MaterialLibraryItem(V2Model):
    id: str
    title: str
    type: str
    thumbnail_label: str
    source: Literal["generated", "template"]
    reusable: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    configuration: dict[str, Any] = Field(default_factory=dict)
    compatible_goal_terms: list[str] = Field(default_factory=list)
    compatible_profile_factor_ids: list[str] = Field(default_factory=list)
    version: int = 1


SessionStatus = Literal["planned", "in_progress", "completed", "draft"]
SessionTrialOutcome = Literal[
    "independent_success", "prompted_success", "incorrect", "no_response",
    "not_observed_unsuccessful", "break_honored", "cancelled"
]
SessionResponseMode = Literal["speech", "AAC", "pointing", "other", "none"]
SessionPromptLevel = Literal[
    "independent", "gesture", "visual", "model", "brief_verbal", "other"
]
PrintPreset = Literal[
    "complete_kit", "teacher_desk", "classroom_materials", "data_and_closeout"
]
PrintTextProfile = Literal["standard", "large"]


class SessionVisualPlanRevision(V2Model):
    planId: str
    materialId: str
    revision: int = Field(ge=1)


class SessionPdfArtifactLineage(V2Model):
    exportId: str
    manifestVersion: int = Field(ge=1)
    rendererVersion: str
    printPreset: PrintPreset
    pageSize: Literal["LETTER", "A4"]
    textProfile: PrintTextProfile = "standard"
    sha256: str


class SessionUseSnapshot(V2Model):
    id: str
    sessionId: str
    learnerId: str
    goalId: str
    goalRevision: int = Field(ge=1)
    goalComparisonKey: str
    operationalizedGoal: str
    lessonSpecId: str
    lessonSpecRevision: int = Field(ge=1)
    packageId: str
    packageRevision: int = Field(ge=1)
    materialRevisions: dict[str, int]
    materialLabels: dict[str, str] = Field(default_factory=dict)
    visualPlanRevisions: list[SessionVisualPlanRevision] = Field(default_factory=list)
    pdfArtifact: SessionPdfArtifactLineage | None = None
    teacherConfirmedContexts: list[PracticeContextItem] = Field(default_factory=list)
    acceptedResponseModes: list[str] = Field(default_factory=list)
    promptLevelDefinitions: list[str] = Field(default_factory=list)
    independenceDefinition: str
    dataMeasures: list[str] = Field(default_factory=list)
    plannedOpportunities: int = Field(ge=1)
    startedAt: datetime
    startedByTeacher: str
    idempotencyKey: str


class SessionRunDraftTrial(V2Model):
    trialId: str
    opportunityNumber: int = Field(ge=1)
    contextId: str | None = None
    contextLabel: str | None = None
    valid: bool | None = None
    outcome: SessionTrialOutcome | None = None
    responseMode: SessionResponseMode | None = None
    promptLevel: SessionPromptLevel | None = None
    latencySeconds: float | None = Field(default=None, ge=0, le=600)
    breakRequested: bool | None = None
    breakDelivered: bool | None = None
    returnedAfterBreak: bool | None = None
    materialIdsUsed: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=500)


SessionRunDraftStatus = Literal[
    "in_progress", "ready_for_closeout", "completed", "discarded"
]


class SessionGeneralizationInput(V2Model):
    status: Literal["observed", "not_observed", "not_attempted"] = "not_attempted"
    people: list[str] = Field(default_factory=list)
    settings: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)


class SessionRunDraftGeneralizationInput(V2Model):
    """Incomplete closeout evidence; the teacher must choose a status."""

    status: Literal["observed", "not_observed", "not_attempted"] | None = None
    people: list[str] = Field(default_factory=list)
    settings: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)


class SessionOutcomeObservations(V2Model):
    engagementLevel: int | None = Field(default=None, ge=0, le=4)
    regulationLevel: int | None = Field(default=None, ge=0, le=4)
    teacherNotes: str = Field(default="", max_length=2000)
    rawCountsConfirmed: bool = False


class SessionRunDraft(V2Model):
    id: str
    sessionId: str
    snapshotId: str
    status: SessionRunDraftStatus = "in_progress"
    trials: list[SessionRunDraftTrial] = Field(default_factory=list, max_length=100)
    generalization: SessionRunDraftGeneralizationInput = Field(
        default_factory=SessionRunDraftGeneralizationInput
    )
    helpfulMaterialIds: list[str] = Field(default_factory=list)
    unhelpfulMaterialIds: list[str] = Field(default_factory=list)
    observations: SessionOutcomeObservations = Field(default_factory=SessionOutcomeObservations)
    activeTrialNumber: int = Field(default=1, ge=1)
    lastSavedAt: datetime = Field(default_factory=utc_now)
    lastMutationIdempotencyKey: str | None = None
    lastMutationHash: str | None = None
    completionIdempotencyKey: str | None = None
    version: int = Field(default=1, ge=1)


class StartSessionRequest(V2Model):
    idempotencyKey: str = Field(min_length=1, max_length=128)
    startedByTeacher: str = Field(min_length=1, max_length=160)
    expectedPackageRevision: int = Field(ge=1)
    contextIds: list[str] = Field(min_length=1)
    pdfExportId: str | None = None
    printPreset: PrintPreset | None = None


class PatchSessionRunDraftRequest(V2Model):
    expectedVersion: int = Field(ge=1)
    idempotencyKey: str = Field(min_length=1, max_length=128)
    status: Literal["in_progress", "ready_for_closeout"] | None = None
    trials: list[SessionRunDraftTrial] | None = Field(default=None, max_length=100)
    generalization: SessionRunDraftGeneralizationInput | None = None
    helpfulMaterialIds: list[str] | None = None
    unhelpfulMaterialIds: list[str] | None = None
    observations: SessionOutcomeObservations | None = None
    activeTrialNumber: int | None = Field(default=None, ge=1)


class CompleteSessionRunDraftRequest(V2Model):
    expectedVersion: int = Field(ge=1)
    idempotencyKey: str = Field(min_length=1, max_length=128)


class DiscardSessionRunDraftRequest(V2Model):
    expectedVersion: int = Field(ge=1)
    idempotencyKey: str = Field(min_length=1, max_length=128)
    confirmed: Literal[True]


class SessionRunStateDto(V2Model):
    snapshot: SessionUseSnapshot
    draft: SessionRunDraft
    packageChanged: bool = False
    packageChangeWarning: str | None = None


class LessonSession(V2Model):
    id: str
    learner_id: str
    goal: str
    status: SessionStatus
    lesson_package_id: str | None = None
    lesson_package_revision: int | None = Field(default=None, ge=1)
    lesson_spec_id: str | None = None
    goal_id: str | None = None
    goal_revision: int | None = Field(default=None, ge=1)
    operationalized_goal: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    idempotency_key: str | None = None
    use_snapshot: SessionUseSnapshot | None = None
    run_draft: SessionRunDraft | None = None
    updated_at: datetime = Field(default_factory=utc_now)
    version: int = Field(default=1, ge=1)


class SessionCreate(V2Model):
    learner_id: str
    goal: str
    status: SessionStatus = "draft"
    lesson_package_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class SessionTrialObservation(V2Model):
    trialId: str
    opportunityNumber: int = Field(ge=1)
    contextId: str
    contextLabel: str
    contextDimension: Literal["activity", "person", "setting", "material"] | None = None
    contextSetting: str = ""
    transitionFrom: str = ""
    transitionTo: str = ""
    valid: bool = True
    outcome: SessionTrialOutcome
    responseMode: SessionResponseMode = "none"
    promptLevel: SessionPromptLevel | None = None
    latencySeconds: float | None = Field(default=None, ge=0, le=600)
    breakRequested: bool = False
    breakDelivered: bool = False
    returnedAfterBreak: bool | None = None
    materialIdsUsed: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def reject_contradictory_trial(self):
        if (self.outcome == "cancelled") != (not self.valid):
            raise ValueError("cancelled trials must be invalid, and invalid trials must be cancelled")
        if self.outcome == "no_response" and self.responseMode != "none":
            raise ValueError("no-response trials cannot record a response mode")
        if self.outcome in {"independent_success", "prompted_success"} and self.responseMode == "none":
            raise ValueError("successful trials require a response mode")
        if self.outcome == "independent_success" and self.promptLevel not in {None, "independent"}:
            raise ValueError("independent success cannot include a prompt")
        if self.outcome == "prompted_success" and self.promptLevel in {None, "independent"}:
            raise ValueError("prompted success requires a non-independent prompt level")
        if self.outcome == "break_honored" and not self.breakDelivered:
            raise ValueError("break-or-stop honored trials must record that the break was delivered")
        if self.breakDelivered and not self.breakRequested and not self.note.strip():
            raise ValueError("a break delivered without a request requires an explanatory note")
        if self.returnedAfterBreak is not None and not self.breakDelivered:
            raise ValueError("return after break cannot be recorded when no break was delivered")
        return self


class SessionOpportunitiesAggregate(V2Model):
    planned: int = Field(ge=0)
    valid: int = Field(ge=0)
    cancelled: int = Field(ge=0)


class SessionResponsesAggregate(V2Model):
    independentSuccessful: int = Field(ge=0)
    promptedSuccessful: int = Field(ge=0)
    incorrect: int = Field(ge=0)
    noResponse: int = Field(ge=0)
    notObservedOrUnsuccessful: int = Field(default=0, ge=0)
    speechSuccessful: int = Field(ge=0)
    aacSuccessful: int = Field(ge=0)
    pointingSuccessful: int = Field(ge=0)
    otherSuccessful: int = Field(ge=0)
    breakOrStopHonored: int = Field(default=0, ge=0)


class SessionPromptingAggregate(V2Model):
    promptLevelCounts: dict[str, int] = Field(default_factory=dict)
    averagePromptLevel: float | None = None
    lowestPromptLevel: SessionPromptLevel | None = None
    highestPromptLevel: SessionPromptLevel | None = None


class SessionLatencyAggregate(V2Model):
    recordedTrialCount: int = Field(ge=0)
    averageSeconds: float | None = Field(default=None, ge=0)
    medianSeconds: float | None = Field(default=None, ge=0)


class SessionGeneralizationAggregate(V2Model):
    status: Literal["observed", "not_observed", "not_attempted"] = "not_attempted"
    contextsAttempted: list[str] = Field(default_factory=list)
    contextsSuccessful: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    settings: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)


class SessionBreakAndReturnAggregate(V2Model):
    breakRequests: int = Field(ge=0)
    breaksDelivered: int = Field(ge=0)
    returnedAfterBreak: int = Field(ge=0)


class SessionMaterialsAggregate(V2Model):
    usedMaterialIds: list[str] = Field(default_factory=list)
    unusedMaterialIds: list[str] = Field(default_factory=list)
    helpfulMaterialIds: list[str] = Field(default_factory=list)
    unhelpfulMaterialIds: list[str] = Field(default_factory=list)


class CompleteSessionRequest(V2Model):
    expectedLessonPackageId: str
    expectedLessonSpecId: str
    expectedGoalId: str
    startedAt: datetime
    completedAt: datetime = Field(default_factory=utc_now)
    trials: list[SessionTrialObservation] = Field(min_length=1, max_length=100)
    generalization: SessionGeneralizationInput = Field(default_factory=SessionGeneralizationInput)
    helpfulMaterialIds: list[str] = Field(default_factory=list)
    unhelpfulMaterialIds: list[str] = Field(default_factory=list)
    observations: SessionOutcomeObservations = Field(default_factory=SessionOutcomeObservations)

    @model_validator(mode="after")
    def validate_completion_request(self):
        if self.completedAt < self.startedAt:
            raise ValueError("completedAt must be on or after startedAt")
        trial_ids = [item.trialId for item in self.trials]
        opportunity_numbers = [item.opportunityNumber for item in self.trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("trial IDs must be unique")
        if len(opportunity_numbers) != len(set(opportunity_numbers)):
            raise ValueError("opportunity numbers must be unique")
        if set(self.helpfulMaterialIds) & set(self.unhelpfulMaterialIds):
            raise ValueError("a material cannot be both helpful and unhelpful")
        return self


class SessionOutcomeDto(V2Model):
    id: str
    sessionId: str
    learnerId: str
    lessonPackageId: str
    lessonPackageRevision: int = Field(ge=1)
    lessonSpecId: str
    goalId: str
    goalRevision: int = Field(ge=1)
    operationalizedGoal: str
    goalComparisonKey: str = ""
    startedAt: datetime
    completedAt: datetime
    opportunities: SessionOpportunitiesAggregate
    responses: SessionResponsesAggregate
    prompting: SessionPromptingAggregate
    latency: SessionLatencyAggregate
    generalization: SessionGeneralizationAggregate
    breakAndReturn: SessionBreakAndReturnAggregate
    materials: SessionMaterialsAggregate
    observations: SessionOutcomeObservations
    trials: list[SessionTrialObservation]
    sessionUseSnapshotId: str | None = None
    sessionUseSnapshot: SessionUseSnapshot | None = None
    createdAt: datetime = Field(default_factory=utc_now)
    version: int = 1


ProgressMetric = Literal[
    "independent_success_rate",
    "prompt_independence_display_score",
    "average_response_latency",
    "generalization_context_count",
    "return_after_break_rate",
]


class GoalProgressPointDetails(V2Model):
    operationalizedGoal: str
    independentSuccessfulCount: int = Field(ge=0)
    promptedSuccessfulCount: int = Field(ge=0)
    responseModeCounts: dict[str, int] = Field(default_factory=dict)
    promptLevelCounts: dict[str, int] = Field(default_factory=dict)
    averagePromptLevel: float | None = None
    averageLatencySeconds: float | None = Field(default=None, ge=0)
    breakRequestCount: int = Field(ge=0)
    breaksDeliveredCount: int = Field(ge=0)
    returnedAfterBreakCount: int = Field(ge=0)
    materialIdsUsed: list[str] = Field(default_factory=list)
    teacherNotes: str = ""


class GoalProgressPoint(V2Model):
    sessionId: str
    completedAt: datetime
    goalId: str
    goalRevision: int = Field(ge=1)
    metric: ProgressMetric
    value: float
    validOpportunityCount: int = Field(ge=0)
    numeratorCount: int = Field(ge=0)
    confidence: Literal["normal", "low"]
    confidenceReason: str | None = None
    lessonPackageId: str
    lessonPackageRevision: int = Field(ge=1)
    contextsAttempted: list[str] = Field(default_factory=list)
    annotation: str | None = None
    details: GoalProgressPointDetails


class GoalContextSummary(V2Model):
    contextKey: str
    contextId: str
    contextLabel: str
    contextDimension: Literal["activity", "person", "setting", "material"] | None = None
    contextSetting: str = ""
    transitionFrom: str = ""
    transitionTo: str = ""
    sessionCount: int = Field(ge=1)
    validOpportunityCount: int = Field(ge=1)
    independentSuccessfulCount: int = Field(ge=0)
    promptedSuccessfulCount: int = Field(ge=0)
    independentSuccessRate: float = Field(ge=0, le=100)
    averagePromptLevel: float | None = Field(default=None, ge=0)
    averageLatencySeconds: float | None = Field(default=None, ge=0)
    firstObservedAt: datetime
    lastObservedAt: datetime
    confidence: Literal["normal", "low"]
    confidenceReasons: list[str] = Field(default_factory=list)
    evidenceSessionIds: list[str] = Field(default_factory=list)
    filterEligible: bool = False


class GoalMaterialUsageSummary(V2Model):
    materialId: str
    materialLabel: str
    sessionCount: int = Field(ge=1)
    validOpportunityCount: int = Field(ge=1)
    independentSuccessfulCount: int = Field(ge=0)
    promptedSuccessfulCount: int = Field(ge=0)
    unsuccessfulOpportunityCount: int = Field(ge=0)
    contextsWithIndependentResponses: list[str] = Field(default_factory=list)
    contextsWithoutIndependentResponses: list[str] = Field(default_factory=list)
    evidenceSessionIds: list[str] = Field(default_factory=list)


class GoalProgressSeries(V2Model):
    learnerId: str
    goalId: str
    goalRevision: int = Field(ge=1)
    operationalizedGoal: str
    metric: ProgressMetric
    points: list[GoalProgressPoint] = Field(default_factory=list)
    trend: Literal[
        "no_data", "insufficient_data", "comparison_only",
        "variable", "improving", "declining", "steady",
    ] = "no_data"
    trendEvidence: list[str] = Field(default_factory=list)
    latestValue: float | None = None
    sessionCount: int = Field(ge=0)
    confidence: Literal["normal", "low"] = "low"
    confidenceReasons: list[str] = Field(default_factory=list)
    activeContextKey: str | None = None
    contextSummaries: list[GoalContextSummary] = Field(default_factory=list)
    materialUsageSummaries: list[GoalMaterialUsageSummary] = Field(default_factory=list)


class GoalProgressSeriesOption(V2Model):
    goalId: str
    goalRevision: int = Field(ge=1)
    operationalizedGoal: str
    sessionCount: int = Field(ge=1)
    latestCompletedAt: datetime


NextSessionRecommendationType = Literal[
    "reuse", "modify_material", "change_context", "prompt_fading",
    "increase_support", "add_generalization", "adjust_duration",
    "collect_more_data", "teacher_question",
]
NextSessionRecommendationStatus = Literal["pending", "accepted", "edited", "rejected"]


class RecommendationEvidence(V2Model):
    sessionId: str
    description: str
    metricPath: str
    observedValue: int | float | str | bool | None = None
    contextId: str | None = None
    contextLabel: str | None = None


class RecommendationReviewEvent(V2Model):
    actorType: Literal["teacher"] = "teacher"
    action: Literal["accepted", "edited", "rejected"]
    teacherText: str | None = None
    reviewedAt: datetime


class NextSessionRecommendationDto(V2Model):
    id: str
    learnerId: str
    goalId: str
    goalRevision: int = Field(ge=1)
    type: NextSessionRecommendationType
    title: str
    recommendation: str
    evidence: list[RecommendationEvidence] = Field(min_length=1)
    confidence: Literal["low", "medium", "high"]
    confidenceReason: str
    teacherReviewRequired: bool = True
    affectedLessonSpecPaths: list[str] = Field(default_factory=list)
    affectedMaterialIds: list[str] = Field(default_factory=list)
    affectedMaterialTypes: list[str] = Field(default_factory=list)
    status: NextSessionRecommendationStatus = "pending"
    teacherEditedText: str | None = None
    ruleId: str
    evidenceFingerprint: str
    createdAt: datetime = Field(default_factory=utc_now)
    reviewedAt: datetime | None = None
    reviewHistory: list[RecommendationReviewEvent] = Field(default_factory=list)
    version: int = 1


class GenerateNextSessionRecommendationsRequest(V2Model):
    goalId: str
    goalRevision: int = Field(ge=1)


class ReviewNextSessionRecommendationRequest(V2Model):
    action: Literal["accepted", "edited", "rejected"]
    teacherEditedText: str | None = None
    expectedVersion: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_teacher_edit(self):
        if self.action == "edited" and not (self.teacherEditedText or "").strip():
            raise ValueError("An edited recommendation requires teacher text")
        if self.action != "edited" and self.teacherEditedText is not None:
            raise ValueError("Teacher-edited text is only accepted with the edited action")
        return self


class RecommendationFieldProvenance(V2Model):
    fieldPath: str
    recommendationId: str
    recommendationStatus: Literal["accepted", "edited"]
    sourceContent: str
    appliedValue: Any = None
    changed: bool


class ProposedLessonSpecRevision(V2Model):
    id: str
    previousLessonSpecId: str
    previousLessonSpecRevision: int = Field(ge=1)
    lessonSpec: LessonSpec
    acceptedRecommendationIds: list[str] = Field(default_factory=list)
    teacherEditedRecommendationContent: dict[str, str] = Field(default_factory=dict)
    changedFields: list[str] = Field(default_factory=list)
    unchangedFields: list[str] = Field(default_factory=list)
    proposedGoalId: str
    proposedGoalRevision: int = Field(ge=1)
    goalSeriesBoundary: Literal["continue", "new"]
    profileRevision: str
    fieldProvenance: list[RecommendationFieldProvenance] = Field(default_factory=list)


class MaterialCompatibilityCheck(V2Model):
    dimension: Literal[
        "goal", "response_modes", "reinforcement", "contexts", "access",
        "profile_revision", "visual_constraints", "approval", "semantic_content",
    ]
    passed: bool
    detail: str


class ReusableMaterialImpact(V2Model):
    materialId: str
    materialRevision: int = Field(ge=1)
    materialType: str
    title: str
    reasonReusable: str
    recommendationIds: list[str] = Field(default_factory=list)
    compatibilityChecks: list[MaterialCompatibilityCheck] = Field(default_factory=list)


class MaterialRevisionImpact(V2Model):
    materialId: str
    materialRevision: int = Field(ge=1)
    materialType: str
    title: str
    affectedFields: list[str] = Field(default_factory=list)
    reason: str
    recommendationIds: list[str] = Field(default_factory=list)
    compatibilityChecks: list[MaterialCompatibilityCheck] = Field(default_factory=list)
    safeToKeepExisting: bool = False


class NewMaterialImpact(V2Model):
    materialType: str
    reason: str
    recommendationIds: list[str] = Field(default_factory=list)
    required: bool = False


class RemovedMaterialImpact(V2Model):
    materialId: str
    materialType: str
    title: str
    reason: str
    recommendationIds: list[str] = Field(default_factory=list)


class NextSessionPlanOverride(V2Model):
    action: Literal["force_regenerate", "keep_existing", "reject_new"]
    materialId: str | None = None
    materialType: str | None = None
    reason: str
    createdAt: datetime = Field(default_factory=utc_now)
    actorType: Literal["teacher"] = "teacher"


class NextSessionMaterialImpactPlanDto(V2Model):
    id: str
    learnerId: str
    previousPackageId: str
    previousPackageRevision: int = Field(ge=1)
    proposedLessonSpecId: str
    proposedLessonSpecRevision: ProposedLessonSpecRevision
    reusableMaterials: list[ReusableMaterialImpact] = Field(default_factory=list)
    materialsToRevise: list[MaterialRevisionImpact] = Field(default_factory=list)
    newMaterialsRequired: list[NewMaterialImpact] = Field(default_factory=list)
    materialsToRemove: list[RemovedMaterialImpact] = Field(default_factory=list)
    blockingIssues: list[str] = Field(default_factory=list)
    overrides: list[NextSessionPlanOverride] = Field(default_factory=list)
    status: Literal["proposed", "package_created"] = "proposed"
    createdPackageId: str | None = None
    createdAt: datetime = Field(default_factory=utc_now)
    version: int = 1


class CreateNextSessionPlanRequest(V2Model):
    expectedPackageRevision: int = Field(ge=1)


class UpdateNextSessionPlanRequest(V2Model):
    action: Literal["force_regenerate", "keep_existing", "reject_new"]
    materialId: str | None = None
    materialType: str | None = None
    reason: str = Field(min_length=1)
    expectedVersion: int = Field(ge=1)


class CreateNextSessionPackageRequest(V2Model):
    expectedPlanVersion: int = Field(ge=1)


class SelectiveMaterialRegenerationRequest(V2Model):
    expectedMaterialVersion: int = Field(ge=1)


class SelectiveScenarioRegenerationRequest(V2Model):
    scenarioId: str
    teacherInstruction: str = Field(default="", max_length=1000)
    expectedMaterialVersion: int = Field(ge=1)


class SessionCompletionTemplateDto(V2Model):
    sessionId: str
    learnerId: str
    lessonPackageId: str
    lessonPackageRevision: int
    lessonSpecId: str
    goalId: str
    goalRevision: int
    operationalizedGoal: str
    plannedOpportunities: int = Field(ge=1)
    contexts: list[PracticeContextItem] = Field(default_factory=list)
    materialIds: list[str] = Field(default_factory=list)
    materialLabels: dict[str, str] = Field(default_factory=dict)
    dataSheetColumns: list[str] = Field(default_factory=list)
    sessionUseSnapshotId: str | None = None


class ProgressObservation(V2Model):
    session_id: str
    learner_id: str
    independence_level: int = Field(ge=0, le=4)
    prompt_level: int = Field(ge=0, le=4)
    engagement_level: int = Field(ge=0, le=4)
    regulation_level: int = Field(ge=0, le=4)
    generalization_contexts: list[str] = Field(default_factory=list)
    notes: str = ""
    observed_at: datetime = Field(default_factory=utc_now)


class ProgressSummary(V2Model):
    learner_id: str
    observation_count: int
    trend: Literal["insufficient_data", "variable", "emerging", "steady"]
    strengths: list[str]
    support_priorities: list[str]
    latest_observation: ProgressObservation | None = None


# Public product DTOs -------------------------------------------------------
#
# These contracts intentionally use the same camelCase attribute names as the
# TypeScript product models. The service layer above may keep idiomatic Python
# names, while routes and future adapters can use these DTOs without requiring
# mapping logic in the frontend.


class LearnerProfileDto(V2Model):
    id: str
    code: str
    age: int
    avatar: str
    tags: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    supportNeeds: list[str] = Field(default_factory=list)
    reinforcementPreferences: list[str] = Field(default_factory=list)
    communicationMode: str
    attentionProfile: str
    notes: str
    strengths: list[str] = Field(default_factory=list)
    sensoryPreferences: list[str] = Field(default_factory=list)
    knownChallenges: list[str] = Field(default_factory=list)
    promptingPreferences: list[str] = Field(default_factory=list)
    currentGoals: list[str] = Field(default_factory=list)
    readingLevel: str = ""
    activityDurationPreference: str = ""
    responseOptions: list[str] = Field(default_factory=list)
    receptiveSupports: list[str] = Field(default_factory=list)
    expressiveSupports: list[str] = Field(default_factory=list)
    environmentalConsiderations: list[str] = Field(default_factory=list)
    effectiveSupports: list[str] = Field(default_factory=list)
    ineffectiveSupports: list[str] = Field(default_factory=list)
    independenceProfile: str = ""
    masteredSkills: list[str] = Field(default_factory=list)
    emergingSkills: list[str] = Field(default_factory=list)
    generalizationProfile: str = ""
    breakPreferences: list[str] = Field(default_factory=list)
    classroomBarriers: list[str] = Field(default_factory=list)
    normalizedProfile: CanonicalLearnerProfile | None = None
    profileSignals: list[ProfileSignal] = Field(default_factory=list)
    unknownFields: list[str] = Field(default_factory=list)
    profileReviewStatus: ProfileReviewStatus = "draft"
    version: int = 1


class LearnerProfileVersionDto(V2Model):
    learnerId: str
    version: int
    reviewStatus: ProfileReviewStatus
    snapshot: LearnerProfileDto


class LearnerRecordDto(V2Model):
    id: str
    learnerId: str
    fileName: str
    fileType: str
    status: RecordStatus
    uploadedAt: str
    extractedText: str
    teacherCorrectedText: str | None = None
    effectiveText: str = ""
    malwareScanStatus: Literal[
        "not_configured", "pending", "clean", "blocked", "failed"
    ] = "not_configured"
    parsingMessage: str = ""
    deletionStatus: Literal["active", "pending", "failed", "deleted"] = "active"
    objectSizeBytes: int | None = None
    version: int = 1


# Resolve the upload intent response's forward reference without moving the
# public DTO beside unrelated learner response models.
RecordUploadIntentResponse.model_rebuild()


class LearnerProfileExtractionDto(V2Model):
    learner: LearnerProfileDto
    records: list[LearnerRecordDto] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    profileSignals: list[ProfileSignal] = Field(default_factory=list)
    unknownFields: list[str] = Field(default_factory=list)
    analyzedRecordCount: int
    status: Literal["complete"] = "complete"
    generationStatus: GenerationStatus | None = None
    generationMetadata: GenerationMetadataDto | None = None
    instructionalConstraintSnapshot: InstructionalConstraintSnapshot | None = None


class LessonDesignDraftDto(V2Model):
    id: str
    learnerId: str
    goalText: str
    responseLevel: str
    scenarios: list[str] = Field(default_factory=list)
    selectedMaterials: list[str] = Field(default_factory=list)
    theme: str
    duration: str
    customNotes: str
    baseline: str = "Unknown — teacher confirmation needed"
    observableResponse: str = ""
    opportunities: int = Field(default=5, ge=1, le=50)
    promptingStart: str = "Wait, then use least-to-most support"
    promptingLimits: str = "Teacher may pause or change prompting at any time"
    reinforcementPlan: str = "Specific praise and learner choice"
    errorCorrection: str = "Neutral feedback, model, and another opportunity"
    dataCollection: str = "Record independence, prompt level, and response outcome"
    generalizationPlan: str = "Practice across examples, people, and settings"
    teacherConstraints: str = ""
    profileRevision: str = ""
    instructionalConstraintSnapshot: InstructionalConstraintSnapshot | None = None
    profileStale: bool = False
    profileStaleMessage: str = ""
    teacherRequest: str = ""
    decisions: list[TeacherDecision] = Field(default_factory=list)
    structuredChanges: list[StructuredTeacherChange] = Field(default_factory=list)
    supplementalSuggestions: list[AIQuestionDto] = Field(default_factory=list)
    packageContentPlan: PackageContentPlan | None = None
    version: int = 1


class AIMessageDto(V2Model):
    id: str
    role: Literal["teacher", "assistant"]
    content: str
    createdAt: str


class AIQuestionOptionDto(V2Model):
    id: str
    label: str
    value: str
    description: str
    icon: str
    recommended: bool
    source: Literal["ai_generated", "teacher_custom"]
    decisionField: Literal["goal", "practice_contexts", "material_requests"] | None = None
    reason: str = ""
    profileFactorIds: list[str] = Field(default_factory=list)
    affects: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    suggestionStatus: Literal[
        "recommended", "optional", "requires_confirmation", "blocked"
    ] = "optional"
    supported: bool = True
    unsupportedReason: str | None = None
    savedForFuture: bool = False


class AIQuestionDto(V2Model):
    id: str
    prompt: str
    helperText: str
    field: Literal[
        "responseLevel",
        "goalText",
        "baseline",
        "scenarios",
        "opportunities",
        "selectedMaterials",
        "theme",
        "duration",
        "promptingStart",
        "promptingLimits",
        "reinforcementPlan",
        "errorCorrection",
        "dataCollection",
        "generalizationPlan",
        "teacherConstraints",
        "customNotes",
    ]
    inputType: Literal["single_select", "multi_select", "free_text", "hybrid"]
    options: list[AIQuestionOptionDto] = Field(default_factory=list)
    selectedOptionIds: list[str] = Field(default_factory=list)
    allowCustomAnswer: bool
    customAnswer: str
    required: bool
    maxSelections: int | None = None


class AIChatStateDto(V2Model):
    conversationId: str
    learnerId: str
    messages: list[AIMessageDto] = Field(default_factory=list)
    questions: list[AIQuestionDto] = Field(default_factory=list)
    draft: LessonDesignDraftDto
    canGenerate: bool
    generationStatus: GenerationStatus | None = None
    generationMetadata: GenerationMetadataDto | None = None


class TeachingStepDto(V2Model):
    id: str
    title: str
    description: str
    duration: str
    teacherAction: str
    learnerAction: str
    phase: str = "practice"
    teacherScript: str | None = None
    expectedLearnerResponse: str = ""
    waitTime: str = "5 seconds"
    promptAction: str = "Use the teacher-confirmed prompt plan"
    reinforcementAction: str = "Acknowledge the target response"
    errorCorrectionAction: str = "Respond neutrally and provide another opportunity"
    dataToRecord: list[str] = Field(default_factory=list)
    transitionCue: str = "Signal the next activity"
    breakOption: str | None = None


class ClassroomRunSheetStepDto(V2Model):
    id: str
    title: str
    duration: str
    teacherScript: str | None = None
    teacherAction: str
    expectedLearnerResponse: str
    waitTime: str
    promptAction: str
    reinforcementAction: str
    errorCorrectionAction: str
    dataToRecord: list[str] = Field(default_factory=list)
    transitionCue: str
    breakOption: str | None = None


class ClassroomRunSheetDto(V2Model):
    learnerCode: str
    goal: str
    totalDuration: str
    communicationModes: list[str] = Field(default_factory=list)
    successCriterion: str
    beforeClassChecklist: list[str] = Field(default_factory=list)
    materialsNeeded: list[str] = Field(default_factory=list)
    materialsSource: Literal["teacher_edit", "included_materials"]
    steps: list[ClassroomRunSheetStepDto] = Field(default_factory=list)
    dataReminder: list[str] = Field(default_factory=list)
    closeout: list[str] = Field(default_factory=list)
    teacherJudgmentNote: str


MaterialValidationStatus = Literal["pending", "passed", "failed"]


class MaterialValidationIssue(V2Model):
    field_path: str
    code: str
    message: str
    remediation: str


class MaterialValidationResult(V2Model):
    status: MaterialValidationStatus = "pending"
    issues: list[MaterialValidationIssue] = Field(default_factory=list)


class StructuredSafetyIssue(V2Model):
    id: str
    scope: Literal["package", "material"]
    material_id: str | None = None
    category: Literal[
        "access", "coercion", "prompting", "reinforcement",
        "emotional_safety", "privacy", "unsupported_assumption",
        "semantic_inconsistency", "other",
    ]
    severity: Literal["warning", "blocking"]
    message: str
    profile_factor_ids: list[str] = Field(default_factory=list)
    lesson_spec_path: str = ""
    material_spec_path: str = ""
    suggested_correction: str
    detected_at_revision: int = Field(ge=1)
    resolved_at_revision: int | None = Field(default=None, ge=1)
    resolution_source: Literal["teacher_edit", "ai_repair", "regeneration"] | None = None


class MaterialSafetyValidationResult(V2Model):
    status: MaterialValidationStatus = "pending"
    issues: list[StructuredSafetyIssue] = Field(default_factory=list)


class MaterialApproval(V2Model):
    status: Literal["not_reviewed", "reviewed", "approved", "rejected"] = "not_reviewed"
    reviewed_revision: int | None = Field(default=None, ge=1)
    approved_revision: int | None = Field(default=None, ge=1)


class MaterialDesignConstraints(V2Model):
    page_size: Literal["Letter", "A4"] = "Letter"
    orientation: Literal["portrait", "landscape"] = "portrait"
    maximum_primary_choices: int | None = Field(default=None, ge=1, le=50)
    layout_requirements: list[str] = Field(default_factory=list)
    prohibited_visual_features: list[str] = Field(default_factory=list)
    prohibited_audio_features: list[str] = Field(default_factory=list)
    motor_access_requirements: list[str] = Field(default_factory=list)
    minimum_touch_target: str | None = None


class MaterialVisualAssetRequest(V2Model):
    id: str
    purpose: str
    description: str
    alt_text: str
    status: Literal["not_requested", "requested", "ready", "failed"] = "not_requested"


VisualAssetRole = Literal[
    "task_item", "scenario", "choice", "concept_exemplar", "first", "then", "token", "reward",
    "communication_symbol", "timer_state", "example", "teacher_reference",
    "decorative",
]
VisualGenerationMethod = Literal[
    "deterministic_svg", "icon_library", "approved_asset", "ai_generated",
    "teacher_uploaded",
]
VisualAssetStatus = Literal[
    "planned", "generating", "ready", "failed", "needs_review",
]


class VisualAssetPlanItem(V2Model):
    id: str
    role: VisualAssetRole
    semantic_key: str
    instructional_purpose: str
    required: bool = True
    generation_method: VisualGenerationMethod
    prompt: str | None = None
    negative_prompt: str | None = None
    alt_text: str
    visible_label: str
    profile_factor_ids: list[str] = Field(default_factory=list)
    design_constraints: dict[str, Any] = Field(default_factory=dict)
    status: VisualAssetStatus = "planned"
    asset_id: str | None = None
    fallback_asset_id: str | None = None
    review_status: Literal["unreviewed", "approved", "rejected"] = "unreviewed"


class VisualAssetPlan(V2Model):
    material_id: str
    material_revision: int = Field(ge=1)
    schema_version: Literal[1] = 1
    visual_items: list[VisualAssetPlanItem] = Field(default_factory=list)
    minimum_required_visuals: int = Field(default=0, ge=0)
    maximum_allowed_visuals: int | None = Field(default=None, ge=0)
    duplicate_policy: str
    text_in_image_allowed: Literal[False] = False


class VisualAssetReplaceRequest(V2Model):
    asset_id: str


class VisualAssetReviewRequest(V2Model):
    action: Literal["approve", "reject"]


class TypedMaterialContent(V2Model):
    """Marker base for closed semantic artifact content contracts."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
        extra="forbid",
    )


class PersonalizedInstructionalActivityContent(TypedMaterialContent):
    task_name: str = Field(min_length=1)
    instructional_objective: str = Field(min_length=1)
    learner_action: str = Field(min_length=1)
    teacher_setup: list[str] = Field(min_length=1)
    required_components: list[str] = Field(min_length=1)
    response_method: list[str] = Field(min_length=1)
    number_of_trials_or_items: int = Field(ge=1, le=100)
    completion_criterion: str = Field(min_length=1)
    answer_key_or_expected_sequence: list[str] = Field(default_factory=list)
    generalization_extension: str = Field(min_length=1)
    motor_access_requirements: list[str] = Field(default_factory=list)
    visual_access_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def executable_task(self):
        placeholders = {"activity", "personalized activity", "practice", "practice the target skill", "target skill"}
        if (
            self.task_name.strip().casefold() in placeholders
            or self.instructional_objective.strip().casefold() in placeholders
            or self.learner_action.strip().casefold() in placeholders
        ):
            raise ValueError("personalized activity must define an executable task")
        return self


class CommunicationCardContent(TypedMaterialContent):
    exact_communication_phrase: str = Field(min_length=1)
    accepted_communication_modes: list[str] = Field(min_length=1)
    card_purpose: str = Field(min_length=1)
    symbol_description: str = Field(min_length=1)
    alternate_text: str = Field(min_length=1)
    touch_target_requirement: str = Field(min_length=1)
    prohibited_imagery: list[str] = Field(default_factory=list)
    teacher_response_after_use: str = Field(min_length=1)

    @field_validator("exact_communication_phrase")
    @classmethod
    def exact_phrase_required(cls, value: str) -> str:
        if value.strip().casefold() in {"", "to be confirmed", "teacher confirmation required", "request"}:
            raise ValueError("an exact communication phrase is required")
        return value


class FirstThenBoardContent(TypedMaterialContent):
    first_task: str = Field(min_length=1)
    then_outcome: str = Field(min_length=1)
    exact_display_text: str = Field(min_length=1)
    first_symbol_description: str = Field(min_length=1)
    then_symbol_description: str = Field(min_length=1)
    completion_criterion: str = Field(min_length=1)
    context: str = Field(min_length=1)
    return_or_transition_instruction: str = Field(min_length=1)

    @model_validator(mode="after")
    def concrete_tasks(self):
        placeholders = {
            "practice", "practice the target skill", "target skill", "activity",
            "teacher-confirmed choice", "teacher confirmed choice", "reward",
        }
        if self.first_task.strip().casefold() in placeholders or self.then_outcome.strip().casefold() in placeholders:
            raise ValueError("FIRST and THEN must be concrete, non-placeholder values")
        return self


class TokenBoardContent(TypedMaterialContent):
    exact_token_count: int = Field(ge=1, le=100)
    token_symbol_or_theme: str = Field(min_length=1)
    earned_reward: str = Field(min_length=1)
    reward_duration_minutes: int | None = Field(default=None, ge=1, le=120)
    pictured_reward_description: str = Field(min_length=1)
    specific_praise: str = Field(min_length=1)
    delivery_instructions: str = Field(min_length=1)
    prohibited_reward_substitutions: list[str] = Field(default_factory=list)

    @field_validator("earned_reward")
    @classmethod
    def concrete_reward(cls, value: str) -> str:
        if value.strip().casefold() in {"reward", "teacher-confirmed reward", "teacher confirmed reward", "to be confirmed"}:
            raise ValueError("a concrete earned reward is required")
        return value


class VisualTimerContent(TypedMaterialContent):
    duration_minutes: int = Field(ge=1, le=120)
    start_label: str = Field(min_length=1)
    end_label: str = Field(min_length=1)
    display_format: str = Field(min_length=1)
    teacher_instruction: str = Field(min_length=1)
    audio_allowed: bool
    return_to_task_cue: str = Field(min_length=1)


class ScenarioCardItem(TypedMaterialContent):
    id: str
    context: str = Field(min_length=1)
    trigger_or_transition: str = Field(min_length=1)
    learner_opportunity: str = Field(min_length=1)
    expected_response: str = Field(min_length=1)
    accepted_modalities: list[str] = Field(min_length=1)
    prompt_sequence: list[str] = Field(default_factory=list)
    consequence_or_reinforcement: str = Field(min_length=1)
    generalization_dimension: Literal["activity", "person", "setting", "material"]
    visual_cue: str = Field(min_length=1)
    teacher_wording: str = Field(min_length=1)
    wait_time_seconds: int = Field(ge=1, le=60)
    break_outcome: str = Field(min_length=1)
    return_support: str = Field(min_length=1)
    generalization_label: str = Field(min_length=1)


class ScenarioCardsContent(TypedMaterialContent):
    scenarios: list[ScenarioCardItem] = Field(min_length=1)

    @field_validator("scenarios")
    @classmethod
    def distinct_scenarios(cls, values: list[ScenarioCardItem]) -> list[ScenarioCardItem]:
        keys = [(item.context.strip().casefold(), item.trigger_or_transition.strip().casefold()) for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("scenario cards must contain distinct scenarios")
        return values


class ChoiceBoardChoice(TypedMaterialContent):
    id: str
    label: str = Field(min_length=1)
    visual_description: str = Field(min_length=1)


class ChoiceBoardContent(TypedMaterialContent):
    prompt_or_question: str = Field(min_length=1)
    choices: list[ChoiceBoardChoice] = Field(min_length=2)
    response_method: list[str] = Field(min_length=1)
    teacher_action_after_selection: str = Field(min_length=1)


class ConceptExemplarItem(TypedMaterialContent):
    id: str
    label: str = Field(min_length=1, max_length=42)
    concept_description: str = Field(min_length=1)


class ConceptExemplarCardsContent(TypedMaterialContent):
    target_labels: list[str] = Field(min_length=1, max_length=2)
    exemplars: list[ConceptExemplarItem] = Field(min_length=3, max_length=8)
    accepted_response_modes: list[str] = Field(min_length=1)
    teacher_instruction: str = Field(min_length=1)
    wait_time_seconds: int = Field(ge=1, le=60)
    independence_rule: str = Field(min_length=1)
    neutral_correction: str = Field(min_length=1)

    @model_validator(mode="after")
    def varied_examples_for_every_target(self):
        targets = [item.strip().casefold() for item in self.target_labels]
        if len(targets) != len(set(targets)):
            raise ValueError("concept targets must be distinct")
        counts = {target: 0 for target in targets}
        concepts: list[str] = []
        for exemplar in self.exemplars:
            key = exemplar.label.strip().casefold()
            if key not in counts:
                raise ValueError("every exemplar label must match a target label")
            counts[key] += 1
            concepts.append(exemplar.concept_description.strip().casefold())
        minimum = 6 if len(targets) == 1 else 4
        if any(count < minimum for count in counts.values()):
            raise ValueError(f"each concept needs at least {minimum} varied exemplars")
        if len(concepts) != len(set(concepts)):
            raise ValueError("concept exemplars must have distinct semantic descriptions")
        return self


class RegulationScaleLevel(TypedMaterialContent):
    order: int = Field(ge=1)
    label: str = Field(min_length=1)
    observable_indicators: list[str] = Field(min_length=1)
    matching_support_option: str = Field(min_length=1)


class RegulationScaleContent(TypedMaterialContent):
    levels: list[RegulationScaleLevel] = Field(min_length=3)
    nonjudgmental_language: str = Field(min_length=1)

    @field_validator("levels")
    @classmethod
    def ordered_distinct_levels(cls, values: list[RegulationScaleLevel]) -> list[RegulationScaleLevel]:
        orders = [item.order for item in values]
        labels = [item.label.strip().casefold() for item in values]
        if orders != sorted(orders) or len(orders) != len(set(orders)) or len(labels) != len(set(labels)):
            raise ValueError("regulation levels must be ordered and have distinct labels")
        return values


class GoalSpecificDataSheetContent(TypedMaterialContent):
    operationalized_target_behavior: str = Field(min_length=1)
    trial_definition: str = Field(min_length=1)
    exact_columns: list[str] = Field(min_length=1)
    response_coding: list[str] = Field(min_length=1)
    prompt_level_definitions: list[str] = Field(min_length=1)
    independence_rule: str = Field(min_length=1)
    summary_calculations_or_totals: list[str] = Field(min_length=1)


class LessonSummaryContent(TypedMaterialContent):
    goal: str = Field(min_length=1)
    observable_target: str = Field(min_length=1)
    contexts_practiced: list[str] = Field(min_length=1)
    response_modes_used: list[str] = Field(min_length=1)
    opportunity_total: int = Field(ge=1)
    successful_opportunity_total: int = Field(ge=0)
    independence_summary: str = Field(min_length=1)
    prompts_used: list[str] = Field(default_factory=list)
    reinforcement_delivered: str = Field(min_length=1)
    regulation_and_break_notes: str = Field(min_length=1)
    next_step: str = Field(min_length=1)
    reporting_fields: list[str] = Field(min_length=1)


class MaterialSpecBase(V2Model):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
        extra="forbid",
    )

    id: str
    schema_version: Literal[1] = 1
    revision: int = Field(default=1, ge=1)
    package_id: str
    lesson_spec_id: str
    lesson_spec_revision: int = Field(ge=1)
    learner_id: str
    artifact_type: str
    title: str
    instructional_purpose: str = Field(min_length=1)
    profile_factor_ids: list[str] = Field(min_length=1)
    decision_ids: list[str] = Field(min_length=1)
    source_material_id: str | None = None
    content: TypedMaterialContent
    design_constraints: MaterialDesignConstraints
    visual_asset_requests: list[MaterialVisualAssetRequest] = Field(default_factory=list)
    teacher_editable_fields: list[str] = Field(min_length=1)
    repair_attempts: int = Field(default=0, ge=0, le=2)
    repair_status: Literal["not_needed", "repaired", "exhausted"] = "not_needed"
    semantic_validation: MaterialValidationResult = Field(default_factory=MaterialValidationResult)
    safety_validation: MaterialSafetyValidationResult = Field(default_factory=MaterialSafetyValidationResult)
    approval: MaterialApproval = Field(default_factory=MaterialApproval)


class PersonalizedInstructionalActivitySpec(MaterialSpecBase):
    artifact_type: Literal["personalized_instructional_activity"] = "personalized_instructional_activity"
    content: PersonalizedInstructionalActivityContent


class CommunicationCardSpec(MaterialSpecBase):
    artifact_type: Literal["communication_card"] = "communication_card"
    content: CommunicationCardContent


class FirstThenBoardSpec(MaterialSpecBase):
    artifact_type: Literal["first_then_board"] = "first_then_board"
    content: FirstThenBoardContent


class TokenBoardSpec(MaterialSpecBase):
    artifact_type: Literal["token_board"] = "token_board"
    content: TokenBoardContent


class VisualTimerSpec(MaterialSpecBase):
    artifact_type: Literal["visual_timer"] = "visual_timer"
    content: VisualTimerContent


class ScenarioCardsSpec(MaterialSpecBase):
    artifact_type: Literal["scenario_cards"] = "scenario_cards"
    content: ScenarioCardsContent


class ChoiceBoardSpec(MaterialSpecBase):
    artifact_type: Literal["choice_board"] = "choice_board"
    content: ChoiceBoardContent


class ConceptExemplarCardsSpec(MaterialSpecBase):
    artifact_type: Literal["concept_exemplar_cards"] = "concept_exemplar_cards"
    content: ConceptExemplarCardsContent


class RegulationScaleSpec(MaterialSpecBase):
    artifact_type: Literal["regulation_scale"] = "regulation_scale"
    content: RegulationScaleContent


class GoalSpecificDataSheetSpec(MaterialSpecBase):
    artifact_type: Literal["goal_specific_data_sheet"] = "goal_specific_data_sheet"
    content: GoalSpecificDataSheetContent


class LessonSummarySpec(MaterialSpecBase):
    artifact_type: Literal["lesson_summary"] = "lesson_summary"
    content: LessonSummaryContent


MaterialSpec = Annotated[
    PersonalizedInstructionalActivitySpec
    | CommunicationCardSpec
    | FirstThenBoardSpec
    | TokenBoardSpec
    | VisualTimerSpec
    | ScenarioCardsSpec
    | ChoiceBoardSpec
    | ConceptExemplarCardsSpec
    | RegulationScaleSpec
    | GoalSpecificDataSheetSpec
    | LessonSummarySpec,
    Field(discriminator="artifact_type"),
]


class MaterialSpecificationBase(V2Model):
    type: str
    purpose: str
    audience: Literal["learner", "teacher", "shared"]
    pageSize: Literal["Letter", "A4"] = "Letter"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margins: str = "0.5 in"
    textLimit: str = "Use brief, plain-language labels"
    imageNeed: Literal["required", "optional", "none"] = "optional"
    contrastGuidance: str = "Use high contrast and avoid relying on color alone"
    printPreparation: list[str] = Field(
        default_factory=lambda: ["Review at actual size", "Check print margins"]
    )
    editableFields: list[str] = Field(default_factory=list)
    requiredContent: list[str] = Field(default_factory=list)
    professionalRules: list[str] = Field(default_factory=list)
    teacherDirections: list[str] = Field(default_factory=list)
    altText: str | None = None


class QuantityCardsSpecification(MaterialSpecificationBase):
    type: Literal["quantity_cards"] = "quantity_cards"
    rangeStart: int = Field(default=1, ge=0, le=20)
    rangeEnd: int = Field(default=5, ge=1, le=20)
    representationStyle: Literal["objects", "dots", "mixed"] = "objects"
    includeNumerals: bool = True


class NumberCardsSpecification(MaterialSpecificationBase):
    type: Literal["number_cards"] = "number_cards"
    rangeStart: int = Field(default=1, ge=0, le=20)
    rangeEnd: int = Field(default=5, ge=1, le=20)
    includeThemeCue: bool = True


class VisualCardSpecification(MaterialSpecificationBase):
    type: Literal["visual_card"] = "visual_card"
    label: str
    visualConcept: str


class ChoiceBoardSpecification(MaterialSpecificationBase):
    type: Literal["choice_board"] = "choice_board"
    options: list[str]


class FirstThenBoardSpecification(MaterialSpecificationBase):
    type: Literal["first_then_board"] = "first_then_board"
    firstText: str
    thenText: str


class HelpCardSpecification(MaterialSpecificationBase):
    type: Literal["help_card"] = "help_card"
    requestText: str


class BreakCardSpecification(MaterialSpecificationBase):
    type: Literal["break_card"] = "break_card"
    requestText: str
    returnCue: str


class TokenBoardSpecification(MaterialSpecificationBase):
    type: Literal["token_board"] = "token_board"
    tokenCount: int = Field(default=5, ge=1, le=20)
    rewardLabel: str


class SortingPageSpecification(MaterialSpecificationBase):
    type: Literal["sorting_page"] = "sorting_page"
    categories: list[str]
    items: list[str]


class MatchingPageSpecification(MaterialSpecificationBase):
    type: Literal["matching_page"] = "matching_page"
    pairs: list[tuple[str, str]]


class ScenarioCardsSpecification(MaterialSpecificationBase):
    type: Literal["scenario_cards"] = "scenario_cards"
    scenarios: list[str]


class SequenceCardsSpecification(MaterialSpecificationBase):
    type: Literal["sequence_cards"] = "sequence_cards"
    steps: list[str]
    numbered: bool = True


class SocialNarrativeSpecification(MaterialSpecificationBase):
    type: Literal["social_narrative"] = "social_narrative"
    situation: str
    responseOptions: list[str]
    supportOptions: list[str]


class CoreWordBoardSpecification(MaterialSpecificationBase):
    type: Literal["core_word_board"] = "core_word_board"
    words: list[str]
    responseModes: list[str]


class VisualScheduleSpecification(MaterialSpecificationBase):
    type: Literal["visual_schedule"] = "visual_schedule"
    steps: list[str]
    completionCue: str = "Move completed step to Done"


class TaskAnalysisCardsSpecification(MaterialSpecificationBase):
    type: Literal["task_analysis_cards"] = "task_analysis_cards"
    steps: list[str]


class EmotionScaleSpecification(MaterialSpecificationBase):
    type: Literal["emotion_scale"] = "emotion_scale"
    levels: list[str]
    regulationOptions: list[str]


class TeacherCueCardSpecification(MaterialSpecificationBase):
    type: Literal["teacher_cue_card"] = "teacher_cue_card"
    cueSteps: list[str]


class DataSheetMaterialSpecification(MaterialSpecificationBase):
    type: Literal["data_sheet"] = "data_sheet"
    columns: list[str]
    summaryCalculation: str


class SessionSummarySpecification(MaterialSpecificationBase):
    type: Literal["session_summary", "summary_template"] = "summary_template"
    prompts: list[str]


class HandoffNoteSpecification(MaterialSpecificationBase):
    type: Literal["handoff_note"] = "handoff_note"
    fields: list[str]


class GenericMaterialProposalSpecification(MaterialSpecificationBase):
    """Typed semantic proposal for a material awaiting a dedicated renderer."""

    fields: list[str] = Field(default_factory=list)


MaterialSpecification = (
    QuantityCardsSpecification
    | NumberCardsSpecification
    | VisualCardSpecification
    | ChoiceBoardSpecification
    | FirstThenBoardSpecification
    | HelpCardSpecification
    | BreakCardSpecification
    | TokenBoardSpecification
    | SortingPageSpecification
    | MatchingPageSpecification
    | ScenarioCardsSpecification
    | SequenceCardsSpecification
    | SocialNarrativeSpecification
    | CoreWordBoardSpecification
    | VisualScheduleSpecification
    | TaskAnalysisCardsSpecification
    | EmotionScaleSpecification
    | TeacherCueCardSpecification
    | DataSheetMaterialSpecification
    | SessionSummarySpecification
    | HandoffNoteSpecification
    | GenericMaterialProposalSpecification
)


class GeneratedMaterialDto(V2Model):
    id: str
    packageId: str
    type: GeneratedMaterialType
    title: str
    status: Literal[
        "generated",
        "ready",
        "validation_failed",
        "safety_review_needed",
        "teacher_review_needed",
        "approved",
        "rejected",
        "superseded",
    ]
    content: dict[str, Any] = Field(default_factory=dict)
    printLayout: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    generationStatus: GenerationStatus | None = None
    generationMetadata: GenerationMetadataDto | None = None
    materialSchemaVersion: Literal[0, 1] = 0
    materialSpec: MaterialSpec | None = None
    visualAssetPlan: VisualAssetPlan | None = None
    specification: MaterialSpecification | None = None

    @model_validator(mode="after")
    def require_versioned_material_spec(self):
        if self.materialSchemaVersion == 1 and self.materialSpec is None:
            raise ValueError("materialSpec is required for materialSchemaVersion 1")
        return self


class PromptingPlanDto(V2Model):
    startingPrompt: str
    permittedHierarchy: list[str]
    waitTime: str
    fadingIntention: str
    reduceSupportCriteria: str
    teacherOverride: str


class ReinforcementPlanDto(V2Model):
    selectedSupport: str
    deliveryTiming: str
    targetResponse: str
    learnerChoice: str
    alternativeWhenIneffective: str
    noCoerciveDeprivation: bool = True


class ErrorCorrectionPlanDto(V2Model):
    neutralResponse: str
    repeatOpportunity: str
    supportAfterRepeatedError: str
    dataRecording: str


class GeneralizationPlanDto(V2Model):
    examples: list[str]
    people: list[str]
    settings: list[str]
    wording: list[str]
    materials: list[str]
    responseFormats: list[str]


class DataSheetSpecificationDto(V2Model):
    columns: list[str]
    summaryCalculation: str


class TeacherAdaptationPlanDto(V2Model):
    signsToPause: list[str]
    tooDifficultSigns: list[str]
    tooEasySigns: list[str]
    howToShorten: str
    howToIncreaseChallenge: str
    requiresTeamReview: list[str]


class SafetyReviewDto(V2Model):
    status: Literal["pass", "needs_review", "blocked"]
    riskLevel: Literal["low", "medium", "high"]
    issues: list[str] = Field(default_factory=list)
    recommendedEdits: list[str] = Field(default_factory=list)
    appliedEdits: list[str] = Field(default_factory=list)
    structuredIssues: list[StructuredSafetyIssue] = Field(default_factory=list)


class StandardsCheckDto(V2Model):
    id: str
    skillId: str
    label: str
    description: str
    severity: Literal["low", "medium", "high"]
    status: Literal["pass", "needs_review", "blocked", "not_applicable"]
    recommendation: str
    version: str = "instructional-quality-v2"
    evidenceLocation: str = "lesson_package"
    explanation: str = ""
    recommendedEdit: str = ""


class QualityScoreItemDto(V2Model):
    id: str
    label: str
    score: int = Field(ge=0, le=2)
    maxScore: int = 2
    status: Literal["pass", "needs_review", "blocked"]
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendedEdits: list[str] = Field(default_factory=list)
    critical: bool = False


class LessonPackageQualityScoreDto(V2Model):
    totalScore: int = Field(ge=0, le=16)
    maxScore: int = 16
    percentage: int = Field(ge=0, le=100)
    overallStatus: Literal["pass", "needs_review", "blocked"]
    items: list[QualityScoreItemDto] = Field(default_factory=list)
    evaluatorVersion: str = "lesson-package-quality-v2"
    teacherReviewRequired: bool = True


class LessonPackageDto(V2Model):
    id: str
    learnerId: str
    draftId: str
    goal: str
    duration: str
    theme: str
    lessonBrief: str
    teachingFlow: list[TeachingStepDto] = Field(default_factory=list)
    materials: list[GeneratedMaterialDto] = Field(default_factory=list)
    summaryTemplate: str
    safetyReview: SafetyReviewDto | None = None
    standardsChecks: list[StandardsCheckDto] = Field(default_factory=list)
    qualityScore: LessonPackageQualityScoreDto | None = None
    documentContent: dict[str, Any] = Field(default_factory=dict)
    aiProvider: str | None = None
    fallbackUsed: bool | None = None
    generationStatus: GenerationStatus | None = None
    generationMetadata: GenerationMetadataDto | None = None
    personalizationSources: list[str] = Field(default_factory=list)
    profileRevision: str = ""
    instructionalConstraintSnapshot: InstructionalConstraintSnapshot | None = None
    teacherDecisions: list[TeacherDecision] = Field(default_factory=list)
    staleOutputs: list[str] = Field(default_factory=list)
    lessonSpec: LessonSpec | None = None
    packageContentPlan: PackageContentPlan | None = None
    validationPolicy: Literal["legacy_compatibility", "strict_v1"] = "legacy_compatibility"
    validationStatus: Literal["pending", "passed", "failed"] = "pending"
    validatedRevision: int | None = Field(default=None, ge=1)
    validatedLessonSpecRevision: int | None = Field(default=None, ge=1)
    status: Literal[
        "generated",
        "validation_failed",
        "safety_review_needed",
        "teacher_review_needed",
        "approved",
        "rejected",
        "superseded",
    ] = "teacher_review_needed"
    targetSkill: str = ""
    observableResponse: str = ""
    baseline: str = "Unknown — teacher confirmation needed"
    objective: str = ""
    successCriterion: str = "Teacher-defined criterion required"
    responseModality: str = ""
    preparationChecklist: list[str] = Field(default_factory=list)
    promptingPlan: PromptingPlanDto | None = None
    reinforcementPlan: ReinforcementPlanDto | None = None
    errorCorrectionPlan: ErrorCorrectionPlanDto | None = None
    generalizationPlan: GeneralizationPlanDto | None = None
    dataSheetSpecification: DataSheetSpecificationDto | None = None
    teacherAdaptation: TeacherAdaptationPlanDto | None = None
    version: int = 1


class LessonPackageUpdateRequest(V2Model):
    lessonBrief: str | None = None
    summaryTemplate: str | None = None
    teachingFlow: list[TeachingStepDto] | None = None
    documentContent: dict[str, Any] | None = None
    expectedVersion: int | None = Field(default=None, ge=1)


class LessonPackageDecisionRequest(V2Model):
    expectedVersion: int = Field(ge=1)
    reason: str = Field(default="", max_length=1000)


class LessonPackageRegenerateSectionRequest(V2Model):
    section: Literal[
        "lessonBrief",
        "teachingFlow",
        "promptingPlan",
        "reinforcementPlan",
        "errorCorrectionPlan",
        "generalizationPlan",
        "dataSheetSpecification",
        "teacherAdaptation",
        "summaryTemplate",
    ]
    expectedVersion: int = Field(ge=1)
    teacherInstructions: str = Field(default="", max_length=2000)


class LessonSectionEditPreviewRequest(V2Model):
    sectionId: str = Field(min_length=1, max_length=120)
    sectionLabel: str = Field(min_length=1, max_length=160)
    currentText: str = Field(min_length=1, max_length=12000)
    instruction: str = Field(min_length=1, max_length=1000)
    expectedVersion: int = Field(ge=1)


class LessonSectionEditPreviewDto(V2Model):
    packageId: str
    sectionId: str
    sectionLabel: str
    beforeText: str
    revisedText: str
    instruction: str
    providerUsed: str
    fallbackUsed: bool = False


class LessonPackageVersionDto(V2Model):
    packageId: str
    version: int
    status: str
    snapshot: LessonPackageDto


class LessonPackageVersionComparisonDto(V2Model):
    packageId: str
    fromVersion: int
    toVersion: int
    changedFields: list[str]
    fromSnapshot: LessonPackageDto
    toSnapshot: LessonPackageDto


class LessonSessionDto(V2Model):
    id: str
    learnerId: str
    goal: str
    status: Literal["planned", "in_progress", "completed", "draft"]
    updatedAt: str
    lessonPackageId: str | None = None
    lessonPackageRevision: int | None = None
    lessonSpecId: str | None = None
    goalId: str | None = None
    goalRevision: int | None = None
    operationalizedGoal: str = ""
    startedAt: str | None = None
    completedAt: str | None = None
    sessionUseSnapshotId: str | None = None
    draftStatus: SessionRunDraftStatus | None = None
    draftVersion: int | None = None
    version: int = Field(default=1, ge=1)


class LessonSessionStatDto(V2Model):
    status: str
    label: str
    count: int
    helperText: str


class LessonSessionSummaryDto(V2Model):
    id: str
    learnerId: str
    goal: str
    status: Literal["planned", "in_progress", "completed", "draft"]
    updatedAt: str
    overview: str
    highlights: list[str] = Field(default_factory=list)
    nextSteps: list[str] = Field(default_factory=list)


class RecentLessonDto(V2Model):
    id: str
    learnerId: str
    title: str
    date: str


class MaterialLibraryItemDto(V2Model):
    id: str
    title: str
    type: str
    thumbnailLabel: str
    source: Literal["generated", "template"]
    reusable: bool
    createdAt: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    compatibleGoalTerms: list[str] = Field(default_factory=list)
    compatibleProfileFactorIds: list[str] = Field(default_factory=list)
    version: int = 1


class MaterialLibraryCreateRequest(V2Model):
    title: str
    type: str
    thumbnailLabel: str
    source: Literal["generated", "template"] = "template"
    reusable: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)
    compatibleGoalTerms: list[str] = Field(default_factory=list)
    compatibleProfileFactorIds: list[str] = Field(default_factory=list)


class LessonDraftMaterialAttachRequest(V2Model):
    materialId: str


class LearnerProgressSummaryDto(V2Model):
    learnerId: str
    currentGoal: str
    accuracyPercent: int
    independencePercent: int
    sessionsPracticed: int
    currentPromptLevel: str
    trend: str
    message: str


class ProgressSignalDto(V2Model):
    id: str
    type: str
    label: str
    description: str
    status: Literal["improving", "stable", "emerging", "needs_support"]


class ProgressDataPointDto(V2Model):
    id: str
    learnerId: str
    sessionDate: str
    goal: str
    opportunities: int
    accuracyPercent: int
    independencePercent: int
    promptLevel: str
    signalsHighlighted: list[str] = Field(default_factory=list)
    teacherNotes: str


class StartLessonChatRequest(V2Model):
    learnerId: str
    resumeExisting: bool = False


class LessonChatMessageRequest(V2Model):
    conversationId: str
    learnerId: str
    message: str
    currentDraft: LessonDesignDraftDto | None = None

    @field_validator("currentDraft", mode="before")
    @classmethod
    def empty_draft_is_none(cls, value: Any) -> Any:
        return None if value == {} else value


class UpdateAIQuestionAnswerRequest(V2Model):
    questionId: str
    selectedOptionIds: list[str] = Field(default_factory=list)
    customAnswer: str
    expectedDraftVersion: int | None = Field(default=None, ge=1)
    saveUnsupportedForFuture: bool = False


class RefreshLessonRecommendationsRequest(V2Model):
    expectedDraftVersion: int = Field(ge=1)


class SafetyCheckRequest(V2Model):
    contentType: str
    learnerId: str
    state: str
    district: str
    generatedContent: dict[str, Any] = Field(default_factory=dict)


class SessionDataRecordRequest(V2Model):
    learnerId: str
    lessonPackageId: str
    goal: str
    opportunities: int
    correct: int
    independent: int
    promptLevel: str
    signalsHighlighted: list[str] = Field(default_factory=list)
    teacherNotes: str


class MaterialUpdateRequest(V2Model):
    title: str
    content: dict[str, Any] = Field(default_factory=dict)
    printLayout: dict[str, Any] = Field(default_factory=dict)
    expectedVersion: int | None = Field(default=None, ge=1)


class MaterialQuickEditRequest(V2Model):
    action: Literal["simplify_wording", "regenerate_artwork", "adjust_reward"]


class LessonPackageExportRequest(V2Model):
    format: Literal["pdf", "docx", "pptx", "zip"] = "zip"
    materialIds: list[str] = Field(default_factory=list)
    reviewedConfirmation: bool = False


class PrintableLessonKitRequest(V2Model):
    materialIds: list[str] = Field(default_factory=list)
    printPreset: Literal[
        "complete_kit", "teacher_desk", "classroom_materials", "data_and_closeout"
    ] = "complete_kit"
    pageSize: Literal["Letter", "A4"] = "Letter"
    locale: str = Field(default="en-US", min_length=2, max_length=20)
    tableOfContents: bool = True
    pageNumbers: bool = True
    textProfile: PrintTextProfile = "standard"
    reviewedConfirmation: Literal[True]


PrintReadinessBlockerCategory = Literal[
    "semantic_validation_failure",
    "safety_validation_failure",
    "pending_visual",
    "failed_optional_visual_with_fallback",
    "failed_required_visual",
    "material_revision_not_reviewed",
    "material_revision_not_approved",
    "package_not_approved",
    "stale_lesson_spec_revision",
    "stale_package_revision",
    "stale_material_revision",
    "stale_visual_plan_revision",
    "generation_job_incomplete",
    "generation_job_failed",
    "storage_download_preparation_failure",
    "renderer_manifest_incompatibility",
]


class PackagePrintReadinessBlocker(V2Model):
    blockerId: str
    category: PrintReadinessBlockerCategory
    severity: Literal["blocking", "warning"] = "blocking"
    materialId: str | None = None
    visualId: str | None = None
    explanation: str
    expectedRevision: int | None = Field(default=None, ge=1)
    currentRevision: int | None = Field(default=None, ge=1)
    expectedLessonSpecRevision: int | None = Field(default=None, ge=1)
    currentLessonSpecRevision: int | None = Field(default=None, ge=1)
    recoveryAction: str
    recoveryRoute: str
    recoveryTargetId: str | None = None
    retryPossible: bool = False


class PackagePrintReadiness(V2Model):
    packageId: str
    packageRevision: int = Field(ge=1)
    lessonSpecId: str
    lessonSpecRevision: int = Field(ge=1)
    ready: bool
    evaluatedAt: str
    materialRevisions: dict[str, int]
    visualPlanRevisions: dict[str, int]
    packageApprovalStatus: str
    blockers: list[PackagePrintReadinessBlocker] = Field(default_factory=list)
    recommendedNextAction: PackagePrintReadinessBlocker | None = None
    rendererVersion: str
    manifestCompatible: bool


class HandoffSectionSelectionDto(V2Model):
    learnerOverview: bool = True
    teachingStrategies: bool = True
    activeGoals: bool = True
    progress: bool = True
    recentSessions: bool = True
    lessonPackages: bool = True
    approvedMaterials: bool = True
    transitionNotes: bool = True


class HandoffDateRangeDto(V2Model):
    startDate: str | None = None
    endDate: str | None = None


class TeacherHandoffExportRequest(V2Model):
    sections: HandoffSectionSelectionDto = Field(
        default_factory=HandoffSectionSelectionDto
    )
    dateRange: HandoffDateRangeDto = Field(default_factory=HandoffDateRangeDto)
    sessionIds: list[str] = Field(default_factory=list)
    packageIds: list[str] = Field(default_factory=list)
    materialIds: list[str] = Field(default_factory=list)
    transitionNotes: str = Field(default="", max_length=5000)
    includePrintableMaterials: bool = True
    pageSize: Literal["Letter", "A4"] = "Letter"
    orientation: Literal["portrait"] = "portrait"
    reviewedConfirmation: Literal[True]


class HandoffExportDataDto(V2Model):
    exportSchemaVersion: Literal["teacher-handoff-v1"] = "teacher-handoff-v1"
    learnerReference: dict[str, Any]
    selectedSections: list[str]
    dateRange: HandoffDateRangeDto
    learnerOverview: dict[str, Any] | None = None
    teachingStrategies: list[str] = Field(default_factory=list)
    activeGoals: list[str] = Field(default_factory=list)
    progressData: list[dict[str, Any]] = Field(default_factory=list)
    recentSessions: list[dict[str, Any]] = Field(default_factory=list)
    lessonPackages: list[dict[str, Any]] = Field(default_factory=list)
    approvedMaterials: list[dict[str, Any]] = Field(default_factory=list)
    transitionNotes: str = ""
    generatedAt: str
    provenance: dict[str, Any]


PrintPackageSectionType = Literal[
    "cover",
    "personalization_summary",
    "teacher_brief",
    "lesson_flow",
    "instructional_material",
    "functional_support",
    "data_collection",
    "lesson_summary",
    "appendix",
]

class PrintPackageManifestSection(V2Model):
    sectionType: PrintPackageSectionType
    title: str = Field(min_length=1, max_length=200)
    materialIds: list[str] = Field(default_factory=list)
    required: bool = True
    pageBreakBefore: bool = True
    includedReason: str = "Included by the selected print preset."


class PrintPackageManifestExclusion(V2Model):
    entryType: Literal["section", "material"]
    entryId: str
    title: str
    reason: str


class PrintSourceApprovalReadinessEvidence(V2Model):
    evaluatedAt: str
    ready: Literal[True]
    packageApprovalStatus: Literal["approved"]
    packageRevision: int = Field(ge=1)
    lessonSpecRevision: int = Field(ge=1)
    materialReviewedRevisions: dict[str, int] = Field(default_factory=dict)
    materialApprovedRevisions: dict[str, int] = Field(default_factory=dict)
    warningBlockerIds: list[str] = Field(default_factory=list)


class PrintPackageManifest(V2Model):
    packageId: str
    packageRevision: int = Field(ge=1)
    lessonSpecId: str
    lessonSpecRevision: int = Field(default=1, ge=1)
    profileRevision: str
    schemaVersion: Literal[2] = 2
    printPreset: PrintPreset = "complete_kit"
    pageSize: Literal["LETTER", "A4"] = "LETTER"
    locale: str = "en-US"
    sections: list[PrintPackageManifestSection]
    excludedEntries: list[PrintPackageManifestExclusion] = Field(default_factory=list)
    materialRevisions: dict[str, int]
    visualPlanRevisions: dict[str, int] = Field(default_factory=dict)
    assetVersions: dict[str, int] = Field(default_factory=dict)
    tableOfContents: bool = True
    pageNumbers: bool = True
    textProfile: PrintTextProfile = "standard"
    generatedAt: str
    rendererVersion: str
    sourceApprovalReadinessEvidence: PrintSourceApprovalReadinessEvidence
    pageCount: int | None = Field(default=None, ge=1)


class PrintPresetInventoryEntry(V2Model):
    entryType: Literal["section", "material"]
    entryId: str
    title: str
    reason: str
    materialType: str | None = None
    revision: int | None = Field(default=None, ge=1)


class PrintPresetPreview(V2Model):
    printPreset: PrintPreset
    displayName: str
    description: str
    isDefault: bool = False
    includedEntries: list[PrintPresetInventoryEntry] = Field(default_factory=list)
    excludedEntries: list[PrintPresetInventoryEntry] = Field(default_factory=list)
    estimatedPageCount: int = Field(ge=1)
    available: bool = True
    unavailableReason: str | None = None


class PrintPresetCatalog(V2Model):
    packageId: str
    packageRevision: int = Field(ge=1)
    pageSize: Literal["LETTER", "A4"]
    textProfile: PrintTextProfile = "standard"
    presets: list[PrintPresetPreview]


GenerationPipelineStage = Literal[
    "planning",
    "material_specification",
    "semantic_validation",
    "repair",
    "visual_planning",
    "image_generation",
    "rendering",
    "safety_validation",
    "pdf_composition",
    "artifact_upload",
    "download_readiness",
]

GenerationWorkStatus = Literal[
    "pending", "in_progress", "completed", "failed", "fallback", "skipped"
]


class GenerationStageState(V2Model):
    stage: GenerationPipelineStage
    status: GenerationWorkStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    startedAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None
    failureCategory: str | None = None
    recoverable: bool = True
    message: str = "Waiting to start."
    durationMs: int | None = Field(default=None, ge=0)


class GenerationVisualState(V2Model):
    visualId: str
    semanticKey: str
    required: bool
    status: GenerationWorkStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    provider: str = ""
    model: str = ""
    fallbackAssetId: str | None = None
    failureCategory: str | None = None
    recoverable: bool = True


class GenerationArtifactState(V2Model):
    artifactId: str
    materialType: str
    required: bool = True
    status: GenerationWorkStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    failureCategory: str | None = None
    recoverable: bool = True
    visuals: list[GenerationVisualState] = Field(default_factory=list)


class GenerationCostMetadata(V2Model):
    estimatedTokens: int = Field(default=0, ge=0)
    actualInputTokens: int | None = Field(default=None, ge=0)
    actualOutputTokens: int | None = Field(default=None, ge=0)
    estimatedVisualCount: int = Field(default=0, ge=0)
    actualVisualCount: int = Field(default=0, ge=0)
    estimatedCost: float = Field(default=0, ge=0)
    actualCost: float | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"


class GenerationJobDto(V2Model):
    jobId: str
    learnerId: str
    draftId: str
    lessonSpecId: str
    lessonSpecRevision: int = Field(ge=1)
    packageContentPlanRevision: int = Field(ge=1)
    packageId: str | None = None
    requestedArtifactIds: list[str] = Field(default_factory=list)
    artifacts: list[GenerationArtifactState] = Field(default_factory=list)
    stages: list[GenerationStageState] = Field(default_factory=list)
    status: Literal[
        "pending", "in_progress", "partially_complete", "completed", "failed"
    ] = "pending"
    attempts: int = Field(default=0, ge=0)
    provider: str = ""
    model: str = ""
    startedAt: str | None = None
    lastUpdatedAt: str = Field(default_factory=lambda: utc_now().isoformat())
    completedAt: str | None = None
    failureCategory: str | None = None
    recoverable: bool = True
    cost: GenerationCostMetadata = Field(default_factory=GenerationCostMetadata)
    idempotencyKey: str
    version: int = 1


class LessonPackageExportJobDto(V2Model):
    exportId: str
    learnerId: str = ""
    packageId: str | None = None
    status: Literal[
        "pending",
        "processing",
        "completed",
        "failed",
        "expired",
        "deleted",
    ] = "pending"
    format: Literal["pdf", "docx", "pptx", "zip"] = "zip"
    progressPercent: int = Field(default=0, ge=0, le=100)
    requestedAt: str = Field(default_factory=lambda: utc_now().isoformat())
    startedAt: str | None = None
    completedAt: str | None = None
    expiresAt: str | None = None
    fileName: str = "teacher-handoff.zip"
    fileSizeBytes: int | None = None
    downloadUrl: str | None = None
    downloadUrlExpiresAt: str | None = None
    errorCode: str | None = None
    message: str = ""
    request: TeacherHandoffExportRequest | None = None
    manifest: list[str] = Field(default_factory=list)
    printPackageManifest: PrintPackageManifest | None = None
    pageCount: int | None = Field(default=None, ge=1)
    artifactSha256: str | None = None
    downloadCount: int = 0
    lastDownloadedAt: str | None = None
    storageObjectKey: str | None = Field(default=None, exclude=True)
    version: int = 1


class HandoffExportDownloadDto(V2Model):
    exportId: str
    downloadUrl: str
    expiresAt: str


class PrintableLessonKitArtifactDto(V2Model):
    artifactId: str
    packageId: str
    packageRevision: int = Field(ge=1)
    manifestVersion: Literal[2] = 2
    printPreset: PrintPreset
    pageSize: Literal["LETTER", "A4"]
    textProfile: PrintTextProfile = "standard"
    materialRevisions: dict[str, int]
    status: Literal["ready"] = "ready"
    filename: str
    contentType: Literal["application/pdf"] = "application/pdf"
    sizeBytes: int = Field(gt=0)
    pageCount: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64)
    downloadUrl: str
    expiresAt: str
    reused: bool = False


class DevAILessonQuestionsRequest(V2Model):
    learnerId: str
    message: str = Field(min_length=1, max_length=4000)


class DevAILessonPackageRequest(V2Model):
    learnerId: str
    goalText: str
    responseLevel: str
    scenarios: list[str] = Field(default_factory=list)
    selectedMaterials: list[str] = Field(default_factory=list)
    theme: str
    duration: str
    customNotes: str


class DevAIStatusDto(V2Model):
    provider: str
    textModel: str
    imageModel: str
    hasApiKey: bool


class DevAILessonQuestionsResponse(V2Model):
    provider: str
    model: str
    fallbackUsed: bool
    questions: list[AIQuestion] = Field(default_factory=list)
    draft: LessonDesignDraft


class DevAILessonPackageResponse(V2Model):
    provider: str
    model: str
    fallbackUsed: bool
    generatedContent: dict[str, Any]


class ImageGenerationRequest(V2Model):
    learnerId: str
    materialType: str
    prompt: str = Field(min_length=1, max_length=4000)
    style: str | None = None
    size: str | None = None


class ImageGenerationResponse(V2Model):
    imageId: str
    status: Literal["ready", "mock"]
    provider: Literal["mock", "openai"]
    model: str
    imageUrl: str | None = None
    imageBase64: str | None = None
    promptUsed: str
    fallbackUsed: bool
    generationStatus: GenerationStatus | None = None
    generationMetadata: GenerationMetadataDto | None = None


class ImageAssetDto(V2Model):
    id: str
    sourceType: Literal[
        "internal", "pexels", "pixabay", "unsplash", "generated", "mock"
    ]
    title: str
    concept: str
    imageUrl: str | None = None
    imageBase64: str | None = None
    storageObjectKey: str | None = None
    thumbnailUrl: str | None = None
    altText: str
    tags: list[str] = Field(default_factory=list)
    licenseInfo: str
    attribution: str | None = None
    providerAssetId: str | None = None
    approved: bool
    safetyStatus: Literal["ready", "needs_review", "blocked"]
    createdAt: str


class ImageSearchRequest(V2Model):
    concept: str = Field(min_length=1, max_length=200)
    materialType: str = Field(min_length=1, max_length=100)
    learnerId: str | None = None
    maxResults: int = Field(default=6, ge=1, le=24)
    allowExternalSearch: bool = True
    allowGeneration: bool = False
    preferredStyle: str | None = None


class ImageCandidateResponse(V2Model):
    concept: str
    materialType: str
    sourceOrder: list[str] = Field(default_factory=list)
    candidates: list[ImageAssetDto] = Field(default_factory=list)
    generationAvailable: bool
    fallbackUsed: bool
    message: str


class ApproveImageAssetRequest(V2Model):
    assetId: str
    materialId: str | None = None
    concept: str | None = None


class GenerateImageCandidateRequest(V2Model):
    learnerId: str
    materialType: str
    concept: str
    prompt: str
    style: str | None = None
    size: str | None = None
