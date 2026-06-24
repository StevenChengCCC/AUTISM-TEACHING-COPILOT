from pydantic import BaseModel, ConfigDict, Field


class ChildProfileCreate(BaseModel):
    organization_id: int | None = None
    code: str = Field(..., examples=["C-001"])
    age: int | None = None
    diagnosis_level: str | None = None
    attention_span_minutes: int | None = None
    communication_mode: str | None = None
    communication_level: str | None = None
    current_level: str = ""
    interests: list[str] = Field(default_factory=list)
    reinforcers: list[str] = Field(default_factory=list)
    preferred_reinforcers: list[str] = Field(default_factory=list)
    prompting_that_works: str = ""
    avoid_notes: str = ""
    behavior_notes: str = ""
    notes: str = ""


class ChildProfileRead(ChildProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ChildProfileUpdate(BaseModel):
    organization_id: int | None = None
    age: int | None = None
    diagnosis_level: str | None = None
    attention_span_minutes: int | None = None
    communication_mode: str | None = None
    communication_level: str | None = None
    current_level: str | None = None
    interests: list[str] | None = None
    reinforcers: list[str] | None = None
    preferred_reinforcers: list[str] | None = None
    prompting_that_works: str | None = None
    avoid_notes: str | None = None
    behavior_notes: str | None = None
    notes: str | None = None


class ProfileQuestion(BaseModel):
    field: str
    question: str
    reason: str


class ProfileCompletenessResult(BaseModel):
    child_id: int
    is_complete: bool
    missing_fields: list[str] = Field(default_factory=list)
    guided_questions: list[ProfileQuestion] = Field(default_factory=list)


class TeachingGoalCreate(BaseModel):
    child_id: int
    target_skill: str
    concept: str | None = None
    status: str = "active"
    notes: str = ""


class TeachingGoalUpdate(BaseModel):
    target_skill: str | None = None
    concept: str | None = None
    status: str | None = None
    mastery_level: int | None = None
    notes: str | None = None


class TeachingGoalRead(TeachingGoalCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mastery_level: int = 0


class ImageNeedRequest(BaseModel):
    child_id: int
    target_skill: str
    concept: str
    needed_count: int = 10
    prefer_real_photos: bool = True
    variation_requirements: list[str] = Field(
        default_factory=lambda: ["颜色变式", "角度变式", "场景变式"]
    )


class ImageCandidate(BaseModel):
    id: int | None = None
    title: str
    source_type: str
    source_url: str | None = None
    thumbnail_url: str | None = None
    local_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    variation_type: str | None = None
    quality_score: int = 0
    license_info: str | None = None
    license_label: str | None = None
    teacher_approved: bool = False
    reason: str | None = None
    generation_prompt: str | None = None


class ImagePipelineResult(BaseModel):
    concept: str
    target_skill: str
    strategy_used: str
    candidates: list[ImageCandidate]
    next_action: str
    missing_count: int = 0
    notes: list[str] = Field(default_factory=list)


class ConfirmImageRequest(BaseModel):
    candidates: list[ImageCandidate]
    approved_indexes: list[int] = Field(default_factory=list)
    skill_target: str
    concept: str


class LessonPlanRequest(BaseModel):
    child_id: int
    goal_id: int | None = None
    target_skill: str
    duration_minutes: int = 25
    print_formats: list[str] = Field(default_factory=lambda: ["a4", "letter"])
    selected_image_asset_ids: list[int] = Field(default_factory=list)


class LessonPlanResponse(BaseModel):
    id: int | None = None
    child_id: int | None = None
    goal_id: int | None = None
    target_skill: str
    duration_minutes: int
    teaching_goal: dict = Field(default_factory=dict)
    segments: list[dict]
    generalization_plan: list[dict]
    reinforcement_plan: dict
    candidate_images: list[ImageCandidate] = Field(default_factory=list)
    downloadable_card_pdf_links: dict[str, str] = Field(default_factory=dict)
    teacher_script: list[str]
    data_recording_sheet: dict
    session_notes_template: dict = Field(default_factory=dict)
    ai_used: bool = False
    cost_saving_notes: list[str] = Field(default_factory=list)


class SessionRecordCreate(BaseModel):
    child_id: int
    goal_id: int | None = None
    target_skill: str
    independent_count: int = 0
    prompted_count: int = 0
    error_count: int = 0
    notes: str = ""


class SessionRecordRead(SessionRecordCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    progress_level: int
    mastery_level: int = 0
    progress_delta: int = 0
    confidence_score: int = 0


class UploadedMaterialCreate(BaseModel):
    child_id: int
    title: str
    material_type: str = "document"
    source_path: str | None = None
    extracted_text: str = ""
    status: str = "uploaded"


class UploadedMaterialUpdate(BaseModel):
    title: str | None = None
    material_type: str | None = None
    source_path: str | None = None
    extracted_text: str | None = None
    status: str | None = None


class UploadedMaterialRead(UploadedMaterialCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class OrganizationCreate(BaseModel):
    name: str
    external_ref: str | None = None


class OrganizationRead(OrganizationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class OrganizationUpdate(BaseModel):
    name: str | None = None
    external_ref: str | None = None


class TeacherCreate(BaseModel):
    organization_id: int | None = None
    display_name: str
    email: str | None = None
    role: str = "teacher"


class TeacherRead(TeacherCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TeacherUpdate(BaseModel):
    organization_id: int | None = None
    display_name: str | None = None
    email: str | None = None
    role: str | None = None


class TeacherChildAccessCreate(BaseModel):
    teacher_id: int
    child_id: int
    permission_level: str = "editor"


class TeacherChildAccessRead(TeacherChildAccessCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TeacherChildAccessUpdate(BaseModel):
    permission_level: str | None = None


class CurriculumContentCreate(BaseModel):
    organization_id: int | None = None
    title: str
    content_type: str = "goal_template"
    content_json: dict = Field(default_factory=dict)
    status: str = "draft"


class CurriculumContentRead(CurriculumContentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class CurriculumContentUpdate(BaseModel):
    organization_id: int | None = None
    title: str | None = None
    content_type: str | None = None
    content_json: dict | None = None
    status: str | None = None


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_teacher_id: int | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    child_id: int | None = None
    metadata_json: str = "{}"
