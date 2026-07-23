import logging
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.auth import CurrentTeacher, get_current_teacher
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
    AuthenticatedTeacherDto,
    ApproveImageAssetRequest,
    ImageAssetDto,
    ImageCandidateResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    ImageSearchRequest,
    GenerateImageCandidateRequest,
    LearnerCreate,
    LearnerProfileDto,
    LearnerProfileVersionDto,
    LearnerProfileExtractionDto,
    LearnerRecordDto,
    LearnerUpdate,
    ProfileConfirmRequest,
    ProfileSignalReviewRequest,
    LessonChatMessageRequest,
    LessonDraftMaterialAttachRequest,
    LessonChatRequest,
    LessonDesignDraft,
    LessonDesignDraftDto,
    LessonPackage,
    LessonPackageDto,
    LessonPackageDecisionRequest,
    LessonPackageRegenerateSectionRequest,
    LessonPackageUpdateRequest,
    LessonPackageVersionComparisonDto,
    LessonPackageVersionDto,
    LessonPackageExportJobDto,
    LessonPackageExportRequest,
    TeacherHandoffExportRequest,
    HandoffExportDownloadDto,
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
    RecordUploadIntentRequest,
    RecordUploadIntentResponse,
    RecordUploadCompleteRequest,
    RecordTextCorrectionRequest,
    RecordDeletionResponse,
    SessionCreate,
    SessionDataRecordRequest,
    StartLessonChatRequest,
    UpdateAIQuestionAnswerRequest,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_progress_service import V2ProgressService
from app.services.v2_record_service import V2RecordService
from app.services.v2_repositories import repositories
from app.services.v2_session_service import V2SessionService
from app.services.v2_handoff_export_service import V2HandoffExportService
from app.services.v2_ai_context_service import build_lesson_generation_context
from app.integrations.private_object_storage import (
    LocalPrivateObjectStorage,
    get_private_object_storage,
)

router = APIRouter(
    prefix="/v2",
    tags=["v2-product"],
    dependencies=[Depends(get_current_teacher)],
)
logger = logging.getLogger(__name__)


def _record_service(
    current: CurrentTeacher = Depends(get_current_teacher),
) -> V2RecordService:
    """Bind record access to the current v2 repository ownership scope.

    Local anonymous demo requests intentionally share the seeded development
    scope. Non-anonymous SQLAlchemy requests receive an owner-specific scope.
    The current header authentication remains a documented demo limitation and
    must be replaced by the production identity round.
    """

    return V2RecordService(repositories)


def _handoff_export_service(
    current: CurrentTeacher = Depends(get_current_teacher),
) -> V2HandoffExportService:
    return V2HandoffExportService(repositories)


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
    return HealthResponse(
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )


@router.get("/auth/me", response_model=AuthenticatedTeacherDto)
def authenticated_teacher(
    current: CurrentTeacher = Depends(get_current_teacher),
) -> AuthenticatedTeacherDto:
    if current.authentication_mode not in {"demo", "cognito"}:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return AuthenticatedTeacherDto(
        subject=str(current.subject or current.id),
        displayName=current.display_name,
        email=current.email,
        organizationId=(
            current.organization_external_id or settings.V2_DEFAULT_ORGANIZATION_ID
        ),
        role=current.role,
        expiresAt=current.expires_at,
        authenticationMode=current.authentication_mode,
    )


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
        questions, draft = provider.generate_lesson_questions(learner, payload.message)
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
    learner = V2LearnerService().get(payload.learnerId)
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
        generated = provider.generate_lesson_package(
            draft, build_lesson_generation_context(learner, draft)
        )
    except RuntimeError:
        logger.warning(
            "Development OpenAI lesson package request failed; using mock fallback"
        )
        provider = MockV2AIProvider()
        generated = provider.generate_lesson_package(
            draft, build_lesson_generation_context(learner, draft)
        )
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
        logger.warning("Development OpenAI image request failed; using mock fallback")
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
            logger.warning("Generated image could not be stored; using mock fallback")
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
            "fallbackUsed": fallback_used or bool(generated.get("fallbackUsed")),
        }
    )


@router.post("/image-assets/candidates", response_model=ImageCandidateResponse)
def get_image_asset_candidates(
    payload: ImageSearchRequest,
) -> ImageCandidateResponse:
    return V2ImageAssetService().get_image_candidates(payload)


@router.post("/image-assets/generate-candidate", response_model=ImageAssetDto)
def generate_image_asset_candidate(
    payload: GenerateImageCandidateRequest,
) -> ImageAssetDto:
    return V2ImageAssetService().generate_candidate(payload)


@router.get("/image-assets", response_model=list[ImageAssetDto])
def list_image_assets(
    concept: str | None = None, approved: bool | None = None
) -> list[ImageAssetDto]:
    return V2ImageAssetService().list_assets(concept, approved)


@router.post("/image-assets/{asset_id}/approve", response_model=ImageAssetDto)
def approve_image_asset(
    asset_id: str, payload: ApproveImageAssetRequest
) -> ImageAssetDto:
    return V2ImageAssetService().approve_asset(asset_id, payload)


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


@router.patch(
    "/learners/{learner_id}/profile-signals/{signal_id}",
    response_model=LearnerProfileDto,
)
def review_profile_signal(
    learner_id: str, signal_id: str, payload: ProfileSignalReviewRequest
) -> LearnerProfileDto:
    return V2LearnerService().review_signal(learner_id, signal_id, payload)


@router.post(
    "/learners/{learner_id}/profile/confirm", response_model=LearnerProfileDto
)
def confirm_learner_profile(
    learner_id: str, payload: ProfileConfirmRequest
) -> LearnerProfileDto:
    return V2LearnerService().confirm_profile(learner_id, payload)


@router.get(
    "/learners/{learner_id}/profile/versions",
    response_model=list[LearnerProfileVersionDto],
)
def list_learner_profile_versions(
    learner_id: str,
) -> list[LearnerProfileVersionDto]:
    return V2LearnerService().list_profile_versions(learner_id)


@router.get("/learners/{learner_id}/records", response_model=list[LearnerRecordDto])
def list_records(
    learner_id: str, service: V2RecordService = Depends(_record_service)
) -> list[LearnerRecordDto]:
    return service.list_dtos_for_learner(learner_id)


@router.post(
    "/learners/{learner_id}/records", response_model=LearnerRecordDto, status_code=201
)
def create_record(
    learner_id: str,
    payload: RecordUploadRequest,
    service: V2RecordService = Depends(_record_service),
) -> LearnerRecordDto:
    """Compatibility endpoint for teacher-pasted text, not binary upload."""

    return service.create_dto(learner_id, payload)


@router.post(
    "/learners/{learner_id}/records/upload-intent",
    response_model=RecordUploadIntentResponse,
    status_code=201,
)
def create_record_upload_intent(
    learner_id: str,
    payload: RecordUploadIntentRequest,
    service: V2RecordService = Depends(_record_service),
) -> RecordUploadIntentResponse:
    return service.create_upload_intent(learner_id, payload)


@router.put("/uploads/local/{token}", status_code=204, include_in_schema=False)
async def development_local_presigned_upload(token: str, request: Request) -> Response:
    """Development-only counterpart to a private S3 presigned PUT URL."""

    if settings.APP_ENV not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Not found")
    storage = get_private_object_storage(settings)
    if not isinstance(storage, LocalPrivateObjectStorage):
        raise HTTPException(status_code=404, detail="Not found")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Upload is too large")
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid Content-Length header"
            ) from exc
    body = await request.body()
    storage.put_presigned(
        token,
        body,
        request.headers.get("content-type", "application/octet-stream"),
    )
    return Response(status_code=204)


@router.post(
    "/learners/{learner_id}/records/{record_id}/complete",
    response_model=LearnerRecordDto,
)
def complete_record_upload(
    learner_id: str,
    record_id: str,
    payload: RecordUploadCompleteRequest,
    service: V2RecordService = Depends(_record_service),
) -> LearnerRecordDto:
    return service.complete_upload(learner_id, record_id, payload)


@router.patch(
    "/learners/{learner_id}/records/{record_id}/extracted-text",
    response_model=LearnerRecordDto,
)
def correct_record_text(
    learner_id: str,
    record_id: str,
    payload: RecordTextCorrectionRequest,
    service: V2RecordService = Depends(_record_service),
) -> LearnerRecordDto:
    return service.save_correction(learner_id, record_id, payload)


@router.delete(
    "/learners/{learner_id}/records/{record_id}",
    response_model=RecordDeletionResponse,
)
def delete_record(
    learner_id: str,
    record_id: str,
    service: V2RecordService = Depends(_record_service),
) -> RecordDeletionResponse:
    return service.delete_record(learner_id, record_id)


@router.get(
    "/learners/{learner_id}/profile-extraction",
    response_model=LearnerProfileExtractionDto,
)
def get_profile_extraction(learner_id: str) -> LearnerProfileExtractionDto:
    return V2ProfileExtractionService().extract(learner_id)


@router.post(
    "/learners/{learner_id}/profile-extraction",
    response_model=LearnerProfileExtractionDto,
    include_in_schema=False,
)
def regenerate_profile_extraction(learner_id: str) -> LearnerProfileExtractionDto:
    return V2ProfileExtractionService().extract(learner_id, force=True)


@router.post("/lesson-chat/start", response_model=AIChatStateDto, status_code=201)
def start_lesson_chat(payload: StartLessonChatRequest) -> AIChatStateDto:
    return V2LessonChatService().start_dto(
        payload.learnerId, resume_existing=payload.resumeExisting
    )


@router.post("/lesson-chat/message", response_model=AIChatStateDto)
def send_lesson_chat_message(
    payload: LessonChatMessageRequest,
) -> AIChatStateDto:
    return V2LessonChatService().submit_message_dto(
        payload.conversationId,
        payload.learnerId,
        payload.message,
    )


@router.patch("/lesson-chat/{conversation_id}/answers", response_model=AIChatStateDto)
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


@router.post("/lesson-chat/{conversation_id}/clear", response_model=AIChatStateDto)
def clear_lesson_chat(conversation_id: str) -> AIChatStateDto:
    return V2LessonChatService().clear_dto(conversation_id)


@router.post("/lesson-chats", response_model=AIChatState, status_code=201)
def start_chat(payload: LessonChatRequest) -> AIChatState:
    return V2LessonChatService().start(payload.learner_id)


@router.get("/lesson-chats/{conversation_id}", response_model=AIChatState)
def get_chat(conversation_id: str) -> AIChatState:
    return V2LessonChatService().get(conversation_id)


@router.post("/lesson-chats/{conversation_id}/messages", response_model=AIChatState)
def submit_lesson_request(
    conversation_id: str, payload: LessonRequestSubmit
) -> AIChatState:
    return V2LessonChatService().submit_request(conversation_id, payload.content)


@router.patch(
    "/lesson-chats/{conversation_id}/questions/{question_id}",
    response_model=AIChatState,
)
def update_question_answer(
    conversation_id: str, question_id: str, payload: QuestionAnswerUpdate
) -> AIChatState:
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


@router.get("/lesson-packages", response_model=list[LessonPackageDto])
def list_lesson_packages(learnerId: str | None = None) -> list[LessonPackageDto]:
    return V2LessonPackageService().list_products(learnerId)


@router.get("/lesson-packages/{package_id}", response_model=LessonPackageDto)
def get_lesson_package(package_id: str) -> LessonPackageDto:
    return V2LessonPackageService().get_product(package_id)


@router.patch("/lesson-packages/{package_id}", response_model=LessonPackageDto)
def update_lesson_package(
    package_id: str, payload: LessonPackageUpdateRequest
) -> LessonPackageDto:
    return V2LessonPackageService().update_product(package_id, payload)


@router.post("/lesson-packages/{package_id}/approve", response_model=LessonPackageDto)
def approve_lesson_package(
    package_id: str, payload: LessonPackageDecisionRequest
) -> LessonPackageDto:
    return V2LessonPackageService().approve_product(package_id, payload)


@router.post("/lesson-packages/{package_id}/reject", response_model=LessonPackageDto)
def reject_lesson_package(
    package_id: str, payload: LessonPackageDecisionRequest
) -> LessonPackageDto:
    return V2LessonPackageService().reject_product(package_id, payload)


@router.post(
    "/lesson-packages/{package_id}/regenerate-section",
    response_model=LessonPackageDto,
)
def regenerate_lesson_package_section(
    package_id: str, payload: LessonPackageRegenerateSectionRequest
) -> LessonPackageDto:
    return V2LessonPackageService().regenerate_section(package_id, payload)


@router.get(
    "/lesson-packages/{package_id}/versions",
    response_model=list[LessonPackageVersionDto],
)
def list_lesson_package_versions(package_id: str) -> list[LessonPackageVersionDto]:
    return V2LessonPackageService().list_product_versions(package_id)


@router.get(
    "/lesson-packages/{package_id}/versions/compare",
    response_model=LessonPackageVersionComparisonDto,
)
def compare_lesson_package_versions(
    package_id: str, fromVersion: int, toVersion: int
) -> LessonPackageVersionComparisonDto:
    return V2LessonPackageService().compare_product_versions(
        package_id, fromVersion, toVersion
    )


@router.post(
    "/lesson-packages/{package_id}/versions/{version}/restore",
    response_model=LessonPackageDto,
)
def restore_lesson_package_version(
    package_id: str, version: int, payload: LessonPackageDecisionRequest
) -> LessonPackageDto:
    return V2LessonPackageService().restore_product_version(
        package_id, version, payload.expectedVersion
    )


@router.get(
    "/lesson-packages/{package_id}/materials",
    response_model=list[GeneratedMaterialDto],
)
def list_generated_materials(package_id: str) -> list[GeneratedMaterialDto]:
    return V2MaterialService().list_generated_dtos(package_id)


@router.patch("/generated-materials/{material_id}", response_model=GeneratedMaterialDto)
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
    package_id: str,
    payload: LessonPackageExportRequest,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> LessonPackageExportJobDto:
    return service.create_for_package(package_id, payload)


@router.post(
    "/learners/{learner_id}/handoff-exports",
    response_model=LessonPackageExportJobDto,
    status_code=201,
)
def create_teacher_handoff_export(
    learner_id: str,
    payload: TeacherHandoffExportRequest,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> LessonPackageExportJobDto:
    return service.create(learner_id, payload)


@router.get("/handoff-exports", response_model=list[LessonPackageExportJobDto])
def list_teacher_handoff_exports(
    learnerId: str | None = None,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> list[LessonPackageExportJobDto]:
    return service.list(learnerId)


@router.get(
    "/handoff-exports/{export_id}", response_model=LessonPackageExportJobDto
)
def get_teacher_handoff_export(
    export_id: str,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> LessonPackageExportJobDto:
    return service.get(export_id)


@router.post(
    "/handoff-exports/{export_id}/retry", response_model=LessonPackageExportJobDto
)
def retry_teacher_handoff_export(
    export_id: str,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> LessonPackageExportJobDto:
    return service.retry(export_id)


@router.post(
    "/handoff-exports/{export_id}/download",
    response_model=HandoffExportDownloadDto,
)
def download_teacher_handoff_export(
    export_id: str,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> HandoffExportDownloadDto:
    return service.create_download(export_id)


@router.delete(
    "/handoff-exports/{export_id}", response_model=LessonPackageExportJobDto
)
def delete_teacher_handoff_export(
    export_id: str,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> LessonPackageExportJobDto:
    return service.delete(export_id)


@router.get("/exports/local/{token}", include_in_schema=False)
def local_teacher_handoff_download(token: str) -> Response:
    storage = get_private_object_storage(settings)
    if not isinstance(storage, LocalPrivateObjectStorage):
        raise HTTPException(status_code=404, detail="Not found")
    body, content_type, download_name = storage.read_presigned_get(token)
    return Response(
        content=body,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


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


@router.post("/lesson-drafts/{draft_id}/materials", response_model=LessonDesignDraftDto)
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


@router.post(
    "/sessions/{session_id}/duplicate", response_model=LessonSessionDto, status_code=201
)
def duplicate_session(session_id: str) -> LessonSessionDto:
    return V2SessionService().duplicate_dto(session_id)


@router.get("/sessions/{session_id}/summary", response_model=LessonSessionSummaryDto)
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


@router.post(
    "/progress-observations", response_model=ProgressObservation, status_code=201
)
def add_progress_observation(payload: ProgressObservation) -> ProgressObservation:
    return V2ProgressService().add_observation(payload)


@router.get("/learners/{learner_id}/progress", response_model=ProgressSummary)
def get_progress_summary(learner_id: str) -> ProgressSummary:
    return V2ProgressService().summarize(learner_id)
