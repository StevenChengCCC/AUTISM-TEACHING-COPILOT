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
    version: Literal["v2-product-mock"] = "v2-product-mock"


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


class LearnerUpdate(V2Model):
    age: int | None = None
    tags: list[str] | None = None
    interests: list[str] | None = None
    support_needs: list[str] | None = None
    reinforcement_preferences: list[str] | None = None
    communication_mode: str | None = None
    attention_profile: str | None = None
    notes: str | None = None


RecordStatus = Literal["processing", "ready", "reviewed"]


class LearnerRecord(V2Model):
    id: str
    learner_id: str
    file_name: str
    file_type: str
    status: RecordStatus
    uploaded_at: datetime
    extracted_text: str = ""


class RecordCreate(V2Model):
    file_name: str
    file_type: str
    pasted_text: str = ""


class RecordUploadRequest(V2Model):
    """JSON-only upload contract until multipart storage/parsing is introduced."""

    fileName: str
    fileType: str
    text: str = ""


class ProfileExtraction(V2Model):
    learner: LearnerProfile
    records: list[LearnerRecord]
    insights: list[str]
    analyzed_record_count: int
    status: Literal["complete"] = "complete"


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
    field: Literal["responseLevel", "scenarios", "selectedMaterials", "customNotes"]
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


class AIChatState(V2Model):
    conversation_id: str
    learner_id: str
    messages: list[AIMessage] = Field(default_factory=list)
    questions: list[AIQuestion] = Field(default_factory=list)
    draft: LessonDesignDraft
    can_generate: bool = False


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


class GeneratedMaterial(V2Model):
    id: str
    package_id: str
    type: Literal[
        "visual_card", "help_card", "token_board", "data_sheet", "summary_template"
    ]
    title: str
    status: MaterialStatus = "ready"
    content: dict[str, Any] = Field(default_factory=dict)
    print_layout: PrintLayout = Field(default_factory=PrintLayout)


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


class LearnerRecordDto(V2Model):
    id: str
    learnerId: str
    fileName: str
    fileType: str
    status: Literal["ready", "reviewed", "processing"]
    uploadedAt: str
    extractedText: str


class LearnerProfileExtractionDto(V2Model):
    learner: LearnerProfileDto
    records: list[LearnerRecordDto] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    analyzedRecordCount: int
    status: Literal["complete"] = "complete"


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
        "scenarios",
        "selectedMaterials",
        "theme",
        "duration",
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


class TeachingStepDto(V2Model):
    id: str
    title: str
    description: str
    duration: str
    teacherAction: str
    learnerAction: str


class GeneratedMaterialDto(V2Model):
    id: str
    packageId: str
    type: Literal[
        "visual_card", "help_card", "token_board", "data_sheet", "summary_template"
    ]
    title: str
    status: Literal["ready", "approved"]
    content: dict[str, Any] = Field(default_factory=dict)
    printLayout: dict[str, Any] = Field(default_factory=dict)


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
    status: Literal["pass", "needs_review", "not_applicable"]
    recommendation: str


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


class MaterialQuickEditRequest(V2Model):
    action: Literal["simplify_wording", "regenerate_artwork", "adjust_reward"]


class LessonPackageExportRequest(V2Model):
    format: Literal["pdf", "docx", "pptx"]
    materialIds: list[str] = Field(default_factory=list)


class LessonPackageExportJobDto(V2Model):
    exportId: str
    status: Literal["ready"] = "ready"
    format: Literal["pdf", "docx", "pptx"]
    downloadUrl: str
