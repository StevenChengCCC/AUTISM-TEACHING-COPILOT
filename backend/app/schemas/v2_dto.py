from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
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


class LearnerProfile(V2Model):
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
    profile_signals: list[ProfileSignal] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    profile_review_status: ProfileReviewStatus = "draft"


class LearnerUpdate(V2Model):
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
    profile_signals: list[ProfileSignal] | None = None
    unknown_fields: list[str] | None = None
    profile_review_status: ProfileReviewStatus | None = None
    expected_version: int | None = Field(default=None, ge=1)


class ProfileSignalReviewRequest(V2Model):
    decision: Literal["confirm", "edit", "reject", "leave_unknown"]
    editedValue: str | None = Field(default=None, max_length=1000)
    expectedVersion: int = Field(ge=1)


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
    version: int = 1


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
    "visual_card",
    "choice_board",
    "first_then_board",
    "help_card",
    "break_card",
    "token_board",
    "sorting_page",
    "matching_page",
    "scenario_cards",
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


SessionStatus = Literal["planned", "in_progress", "completed", "draft"]


class LessonSession(V2Model):
    id: str
    learner_id: str
    goal: str
    status: SessionStatus
    updated_at: datetime = Field(default_factory=utc_now)


class SessionCreate(V2Model):
    learner_id: str
    goal: str
    status: SessionStatus = "draft"


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
    altText: str | None = None


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


MaterialSpecification = (
    VisualCardSpecification
    | ChoiceBoardSpecification
    | FirstThenBoardSpecification
    | HelpCardSpecification
    | BreakCardSpecification
    | TokenBoardSpecification
    | SortingPageSpecification
    | MatchingPageSpecification
    | ScenarioCardsSpecification
    | TeacherCueCardSpecification
    | DataSheetMaterialSpecification
    | SessionSummarySpecification
    | HandoffNoteSpecification
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
    specification: MaterialSpecification | None = None


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
    columns: list[
        Literal[
            "opportunity",
            "independent",
            "prompted",
            "incorrect",
            "no_response",
            "prompt_level",
            "latency",
            "notes",
        ]
    ]
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


class StandardsCheckDto(V2Model):
    id: str
    skillId: str
    label: str
    description: str
    severity: Literal["low", "medium", "high"]
    status: Literal["pass", "needs_review", "blocked", "not_applicable"]
    recommendation: str
    version: str = "instructional-quality-v1"
    evidenceLocation: str = "lesson_package"
    explanation: str = ""
    recommendedEdit: str = ""


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
    documentContent: dict[str, Any] = Field(default_factory=dict)
    aiProvider: str | None = None
    fallbackUsed: bool | None = None
    generationStatus: GenerationStatus | None = None
    generationMetadata: GenerationMetadataDto | None = None
    personalizationSources: list[str] = Field(default_factory=list)
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


class MaterialLibraryCreateRequest(V2Model):
    title: str
    type: str
    thumbnailLabel: str
    source: Literal["generated", "template"] = "template"
    reusable: bool = True


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
    downloadCount: int = 0
    lastDownloadedAt: str | None = None
    storageObjectKey: str | None = Field(default=None, exclude=True)
    version: int = 1


class HandoffExportDownloadDto(V2Model):
    exportId: str
    downloadUrl: str
    expiresAt: str


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
