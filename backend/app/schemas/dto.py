from pydantic import BaseModel, ConfigDict, Field

class ChildProfileCreate(BaseModel):
    code: str = Field(..., examples=["C-001"])
    age: int | None = None
    diagnosis_level: str | None = None
    attention_span_minutes: int | None = None
    communication_level: str | None = None
    interests: list[str] = Field(default_factory=list)
    reinforcers: list[str] = Field(default_factory=list)
    behavior_notes: str = ""
    notes: str = ""

class ChildProfileRead(ChildProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class ImageNeedRequest(BaseModel):
    child_id: int
    target_skill: str
    concept: str
    needed_count: int = 10
    prefer_real_photos: bool = True
    variation_requirements: list[str] = Field(default_factory=lambda: ["颜色变式", "角度变式", "场景变式"])

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
    target_skill: str
    duration_minutes: int = 25
    selected_image_asset_ids: list[int] = Field(default_factory=list)

class LessonPlanResponse(BaseModel):
    id: int | None = None
    target_skill: str
    duration_minutes: int
    teaching_goal: dict = Field(default_factory=dict)
    segments: list[dict]
    generalization_plan: list[dict]
    reinforcement_plan: dict
    candidate_images: list[ImageCandidate] = Field(default_factory=list)
    teacher_script: list[str]
    data_recording_sheet: dict
    session_notes_template: dict = Field(default_factory=dict)
    ai_used: bool = False
    cost_saving_notes: list[str] = Field(default_factory=list)

class SessionRecordCreate(BaseModel):
    child_id: int
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
