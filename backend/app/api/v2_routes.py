import logging
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.integrations.ai_provider import get_v2_ai_provider
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.integrations.openai_provider import OpenAIV2AIProvider

from app.schemas.v2_dto import (
    AIChatState,
    AIChatStateDto,
    DevAILessonPackageRequest,
    DevAILessonPackageResponse,
    DevAILessonQuestionsRequest,
    DevAILessonQuestionsResponse,
    DevAIStatusDto,
    GeneratedMaterial,
    GeneratedMaterialDto,
    HealthResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    LearnerCreate,
    LearnerProfileDto,
    LearnerProfileExtractionDto,
    LearnerRecordDto,
    LearnerUpdate,
    LessonChatMessageRequest,
    LessonDraftMaterialAttachRequest,
    LessonChatRequest,
    LessonDesignDraft,
    LessonDesignDraftDto,
    LessonPackage,
    LessonPackageDto,
    LessonPackageExportJobDto,
    LessonPackageExportRequest,
    LessonRequestSubmit,
    LessonSession,
    LessonSessionDto,
    LessonSessionStatDto,
    LessonSessionSummaryDto,
    MaterialLibraryItem,
    MaterialLibraryCreateRequest,
    MaterialLibraryItemDto,
    MaterialQuickEditRequest,
    MaterialUpdate,
    MaterialUpdateRequest,
    LearnerProgressSummaryDto,
    ProgressDataPointDto,
    ProgressSignalDto,
    RecentLessonDto,
    ProgressObservation,
    ProgressSummary,
    QuestionAnswerUpdate,
    RecordUploadRequest,
    SessionCreate,
    SessionDataRecordRequest,
    StartLessonChatRequest,
    UpdateAIQuestionAnswerRequest,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_progress_service import V2ProgressService
from app.services.v2_record_service import V2RecordService
from app.services.v2_session_service import V2SessionService

router = APIRouter(prefix="/v2", tags=["v2-product"])
logger = logging.getLogger(__name__)


def _require_development() -> None:
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=404, detail="Not found")


def _provider_with_dev_fallback():
    try:
        return get_v2_ai_provider(settings), False
    except RuntimeError:
        logger.warning(
            "Configured development AI provider is unavailable; using mock fallback"
        )
        return MockV2AIProvider(), True


def _save_development_image(image_base64: str) -> str:
    try:
        image_bytes = b64decode(image_base64, validate=True)
    except (Base64Error, ValueError) as exc:
        raise ValueError("Generated image data was invalid") from exc
    if not image_bytes or len(image_bytes) > 25 * 1024 * 1024:
        raise ValueError("Generated image data exceeded the development storage limit")
    output_dir = Path(settings.STORAGE_DIR) / "generated-images"
    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4().hex}.png"
    (output_dir / file_name).write_bytes(image_bytes)
    return f"/storage/generated-images/{file_name}"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/dev/ai-status",
    response_model=DevAIStatusDto,
    dependencies=[Depends(_require_development)],
)
def development_ai_status() -> DevAIStatusDto:
    return DevAIStatusDto(
        provider=settings.AI_PROVIDER,
        textModel=settings.OPENAI_TEXT_MODEL,
        imageModel=settings.OPENAI_IMAGE_MODEL,
        hasApiKey=bool(settings.reveal(settings.OPENAI_API_KEY)),
    )


@router.post(
    "/dev/test-ai-lesson-questions",
    response_model=DevAILessonQuestionsResponse,
    dependencies=[Depends(_require_development)],
)
def development_test_ai_lesson_questions(
    payload: DevAILessonQuestionsRequest,
) -> DevAILessonQuestionsResponse:
    learner = V2LearnerService().get(payload.learnerId)
    provider, fallback_used = _provider_with_dev_fallback()
    try:
        questions, draft = provider.generate_lesson_questions(
            learner, payload.message
        )
    except RuntimeError:
        logger.warning(
            "Development OpenAI lesson question request failed; using mock fallback"
        )
        provider = MockV2AIProvider()
        questions, draft = provider.generate_lesson_questions(learner, payload.message)
        fallback_used = True
    if isinstance(provider, OpenAIV2AIProvider):
        fallback_used = fallback_used or provider.last_fallback_used
    return DevAILessonQuestionsResponse(
        provider=settings.AI_PROVIDER,
        model=settings.OPENAI_TEXT_MODEL,
        fallbackUsed=fallback_used,
        questions=questions,
        draft=draft,
    )


@router.post(
    "/dev/test-ai-lesson-package",
    response_model=DevAILessonPackageResponse,
    dependencies=[Depends(_require_development)],
)
def development_test_ai_lesson_package(
    payload: DevAILessonPackageRequest,
) -> DevAILessonPackageResponse:
    V2LearnerService().get(payload.learnerId)
    draft = LessonDesignDraftDto(
        id=f"dev-draft-{payload.learnerId}",
        learnerId=payload.learnerId,
        goalText=payload.goalText,
        responseLevel=payload.responseLevel,
        scenarios=payload.scenarios,
        selectedMaterials=payload.selectedMaterials,
        theme=payload.theme,
        duration=payload.duration,
        customNotes=payload.customNotes,
    )
    provider, fallback_used = _provider_with_dev_fallback()
    try:
        generated = provider.generate_lesson_package(draft)
    except RuntimeError:
        logger.warning(
            "Development OpenAI lesson package request failed; using mock fallback"
        )
        provider = MockV2AIProvider()
        generated = provider.generate_lesson_package(draft)
        fallback_used = True
    if isinstance(provider, OpenAIV2AIProvider):
        fallback_used = fallback_used or provider.last_fallback_used
    return DevAILessonPackageResponse(
        provider=settings.AI_PROVIDER,
        model=settings.OPENAI_TEXT_MODEL,
        fallbackUsed=fallback_used,
        generatedContent=generated,
    )


@router.post(
    "/dev/test-image-generation",
    response_model=ImageGenerationResponse,
    dependencies=[Depends(_require_development)],
)
def development_test_image_generation(
    payload: ImageGenerationRequest,
) -> ImageGenerationResponse:
    learner = V2LearnerService().get(payload.learnerId)
    provider, fallback_used = _provider_with_dev_fallback()
    try:
        generated = provider.generate_material_image(
            learner,
            payload.materialType,
            payload.prompt,
            payload.style,
            payload.size,
        )
    except RuntimeError:
        logger.warning(
            "Development OpenAI image request failed; using mock fallback"
        )
        provider = MockV2AIProvider()
        generated = provider.generate_material_image(
            learner,
            payload.materialType,
            payload.prompt,
            payload.style,
            payload.size,
        )
        fallback_used = True
    if isinstance(provider, OpenAIV2AIProvider):
        fallback_used = fallback_used or provider.last_fallback_used
    image_base64 = generated.get("imageBase64")
    if image_base64:
        try:
            generated["imageUrl"] = _save_development_image(image_base64)
            generated["imageBase64"] = None
        except ValueError:
            logger.warning(
                "Generated image could not be stored; using mock fallback"
            )
            generated = MockV2AIProvider().generate_material_image(
                learner,
                payload.materialType,
                payload.prompt,
                payload.style,
                payload.size,
            )
            fallback_used = True
    configured_provider = "openai" if settings.AI_PROVIDER == "openai" else "mock"
    return ImageGenerationResponse.model_validate(
        {
            **generated,
            "provider": configured_provider,
            "model": settings.OPENAI_IMAGE_MODEL,
            "fallbackUsed": fallback_used
            or bool(generated.get("fallbackUsed")),
        }
    )


@router.get("/learners", response_model=list[LearnerProfileDto])
def list_learners() -> list[LearnerProfileDto]:
    return V2LearnerService().list_dtos()


@router.post("/learners", response_model=LearnerProfileDto, status_code=201)
def create_learner(payload: LearnerCreate) -> LearnerProfileDto:
    return V2LearnerService().create_dto(payload)


@router.get("/learners/{learner_id}", response_model=LearnerProfileDto)
def get_learner(learner_id: str) -> LearnerProfileDto:
    return V2LearnerService().get_dto(learner_id)


@router.patch("/learners/{learner_id}", response_model=LearnerProfileDto)
def update_learner(learner_id: str, payload: LearnerUpdate) -> LearnerProfileDto:
    return V2LearnerService().update_dto(learner_id, payload)


@router.get("/learners/{learner_id}/records", response_model=list[LearnerRecordDto])
def list_records(learner_id: str) -> list[LearnerRecordDto]:
    return V2RecordService().list_dtos_for_learner(learner_id)


@router.post("/learners/{learner_id}/records", response_model=LearnerRecordDto, status_code=201)
def create_record(
    learner_id: str, payload: RecordUploadRequest
) -> LearnerRecordDto:
    return V2RecordService().create_dto(learner_id, payload)


@router.get(
    "/learners/{learner_id}/profile-extraction",
    response_model=LearnerProfileExtractionDto,
)
@router.post(
    "/learners/{learner_id}/profile-extraction",
    response_model=LearnerProfileExtractionDto,
    include_in_schema=False,
)
def extract_profile(learner_id: str) -> LearnerProfileExtractionDto:
    return V2ProfileExtractionService().extract(learner_id)


@router.post("/lesson-chat/start", response_model=AIChatStateDto, status_code=201)
def start_lesson_chat(payload: StartLessonChatRequest) -> AIChatStateDto:
    return V2LessonChatService().start_dto(payload.learnerId)


@router.post("/lesson-chat/message", response_model=AIChatStateDto)
def send_lesson_chat_message(
    payload: LessonChatMessageRequest,
) -> AIChatStateDto:
    return V2LessonChatService().submit_message_dto(
        payload.conversationId,
        payload.learnerId,
        payload.message,
    )


@router.patch(
    "/lesson-chat/{conversation_id}/answers", response_model=AIChatStateDto
)
def update_lesson_chat_answer(
    conversation_id: str, payload: UpdateAIQuestionAnswerRequest
) -> AIChatStateDto:
    return V2LessonChatService().update_answer_dto(
        conversation_id,
        payload.questionId,
        QuestionAnswerUpdate(
            selected_option_ids=payload.selectedOptionIds,
            custom_answer=payload.customAnswer,
        ),
    )


@router.post(
    "/lesson-chat/{conversation_id}/clear", response_model=AIChatStateDto
)
def clear_lesson_chat(conversation_id: str) -> AIChatStateDto:
    return V2LessonChatService().clear_dto(conversation_id)


@router.post("/lesson-chats", response_model=AIChatState, status_code=201)
def start_chat(payload: LessonChatRequest) -> AIChatState:
    return V2LessonChatService().start(payload.learner_id)


@router.get("/lesson-chats/{conversation_id}", response_model=AIChatState)
def get_chat(conversation_id: str) -> AIChatState:
    return V2LessonChatService().get(conversation_id)


@router.post("/lesson-chats/{conversation_id}/messages", response_model=AIChatState)
def submit_lesson_request(conversation_id: str, payload: LessonRequestSubmit) -> AIChatState:
    return V2LessonChatService().submit_request(conversation_id, payload.content)


@router.patch("/lesson-chats/{conversation_id}/questions/{question_id}", response_model=AIChatState)
def update_question_answer(conversation_id: str, question_id: str, payload: QuestionAnswerUpdate) -> AIChatState:
    return V2LessonChatService().update_answer(conversation_id, question_id, payload)


@router.post(
    "/lesson-packages/generate", response_model=LessonPackageDto, status_code=201
)
def generate_product_lesson_package(
    draft: LessonDesignDraftDto,
) -> LessonPackageDto:
    return V2LessonPackageService().generate_product(draft)


@router.post("/lesson-packages", response_model=LessonPackageDto, status_code=201)
def generate_lesson_package(draft: LessonDesignDraftDto) -> LessonPackageDto:
    """Compatibility alias for the initial Backend v2 route."""

    return V2LessonPackageService().generate_product(draft)


@router.get("/lesson-packages/{package_id}", response_model=LessonPackageDto)
def get_lesson_package(package_id: str) -> LessonPackageDto:
    return V2LessonPackageService().get_product(package_id)


@router.get(
    "/lesson-packages/{package_id}/materials",
    response_model=list[GeneratedMaterialDto],
)
def list_generated_materials(package_id: str) -> list[GeneratedMaterialDto]:
    return V2MaterialService().list_generated_dtos(package_id)


@router.patch(
    "/generated-materials/{material_id}", response_model=GeneratedMaterialDto
)
def update_generated_material(
    material_id: str, payload: MaterialUpdateRequest
) -> GeneratedMaterialDto:
    return V2MaterialService().update_generated(material_id, payload)


@router.post(
    "/generated-materials/{material_id}/approve",
    response_model=GeneratedMaterialDto,
)
def approve_generated_material(material_id: str) -> GeneratedMaterialDto:
    return V2MaterialService().approve_generated(material_id)


@router.post(
    "/generated-materials/{material_id}/quick-edit",
    response_model=GeneratedMaterialDto,
)
def quick_edit_generated_material(
    material_id: str, payload: MaterialQuickEditRequest
) -> GeneratedMaterialDto:
    return V2MaterialService().quick_edit_generated(material_id, payload)


@router.post(
    "/lesson-packages/{package_id}/export",
    response_model=LessonPackageExportJobDto,
)
def export_lesson_package(
    package_id: str, payload: LessonPackageExportRequest
) -> LessonPackageExportJobDto:
    return V2MaterialService().create_export_job(package_id, payload)


@router.patch("/materials/{material_id}", response_model=GeneratedMaterial)
def update_material(material_id: str, payload: MaterialUpdate) -> GeneratedMaterial:
    return V2MaterialService().update(material_id, payload)


@router.get("/materials", response_model=list[MaterialLibraryItemDto])
def list_material_library() -> list[MaterialLibraryItemDto]:
    return V2MaterialService().list_library_dtos()


@router.post("/materials", response_model=MaterialLibraryItemDto, status_code=201)
def create_material_library_item(
    payload: MaterialLibraryCreateRequest,
) -> MaterialLibraryItemDto:
    return V2MaterialService().create_library_item(payload)


@router.post(
    "/materials/{material_id}/duplicate",
    response_model=MaterialLibraryItemDto,
    status_code=201,
)
def duplicate_material_library_item(material_id: str) -> MaterialLibraryItemDto:
    return V2MaterialService().duplicate_library_item(material_id)


@router.post(
    "/lesson-drafts/{draft_id}/materials", response_model=LessonDesignDraftDto
)
def attach_material_to_lesson_draft(
    draft_id: str, payload: LessonDraftMaterialAttachRequest
) -> LessonDesignDraftDto:
    return V2MaterialService().attach_to_lesson_draft(draft_id, payload)


@router.get("/sessions", response_model=list[LessonSessionDto])
def list_sessions() -> list[LessonSessionDto]:
    return V2SessionService().list_dtos()


@router.get("/sessions/stats", response_model=list[LessonSessionStatDto])
def get_session_stats() -> list[LessonSessionStatDto]:
    return V2SessionService().stats()


@router.post("/sessions", response_model=LessonSessionDto, status_code=201)
def create_session(payload: SessionCreate) -> LessonSessionDto:
    return V2SessionService().create_dto(payload)


@router.post("/sessions/{session_id}/duplicate", response_model=LessonSessionDto, status_code=201)
def duplicate_session(session_id: str) -> LessonSessionDto:
    return V2SessionService().duplicate_dto(session_id)


@router.get(
    "/sessions/{session_id}/summary", response_model=LessonSessionSummaryDto
)
def get_session_summary(session_id: str) -> LessonSessionSummaryDto:
    return V2SessionService().summary(session_id)


@router.get(
    "/learners/{learner_id}/recent-lessons", response_model=list[RecentLessonDto]
)
def get_recent_lessons(learner_id: str) -> list[RecentLessonDto]:
    return V2SessionService().recent_lessons(learner_id)


@router.get(
    "/learners/{learner_id}/progress-summary",
    response_model=LearnerProgressSummaryDto,
)
def get_product_progress_summary(learner_id: str) -> LearnerProgressSummaryDto:
    return V2ProgressService().product_summary(learner_id)


@router.get(
    "/learners/{learner_id}/progress-signals",
    response_model=list[ProgressSignalDto],
)
def get_product_progress_signals(learner_id: str) -> list[ProgressSignalDto]:
    return V2ProgressService().product_signals(learner_id)


@router.get(
    "/learners/{learner_id}/progress-data",
    response_model=list[ProgressDataPointDto],
)
def get_product_progress_data(learner_id: str) -> list[ProgressDataPointDto]:
    return V2ProgressService().product_data(learner_id)


@router.post("/session-data", response_model=LearnerProgressSummaryDto, status_code=201)
def record_session_data(
    payload: SessionDataRecordRequest,
) -> LearnerProgressSummaryDto:
    return V2ProgressService().record_session_data(payload)


@router.post("/progress-observations", response_model=ProgressObservation, status_code=201)
def add_progress_observation(payload: ProgressObservation) -> ProgressObservation:
    return V2ProgressService().add_observation(payload)


@router.get("/learners/{learner_id}/progress", response_model=ProgressSummary)
def get_progress_summary(learner_id: str) -> ProgressSummary:
    return V2ProgressService().summarize(learner_id)
