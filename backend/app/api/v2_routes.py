import logging
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)

from app.core.auth import CurrentTeacher, get_current_teacher
from app.core.auth_context import (
    AuthenticatedScope,
    get_authenticated_scope,
    reset_authenticated_scope,
    set_authenticated_scope,
)
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
    GenerationJobDto,
    GoalProgressSeries,
    GoalProgressSeriesOption,
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
    ProfileFactorReviewRequest,
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
    LessonSectionEditPreviewDto,
    LessonSectionEditPreviewRequest,
    LessonPackageUpdateRequest,
    LessonPackageVersionComparisonDto,
    LessonPackageVersionDto,
    LessonPackageExportJobDto,
    LessonPackageExportRequest,
    PrintableLessonKitArtifactDto,
    PrintableLessonKitRequest,
    PrintPresetCatalog,
    PackagePrintReadiness,
    TeacherHandoffExportRequest,
    HandoffExportDownloadDto,
    LessonRequestSubmit,
    LessonSession,
    LessonSessionDto,
    LessonSessionStatDto,
    LessonSessionSummaryDto,
    MaterialLibraryItem,
    VisualAssetReplaceRequest,
    VisualAssetReviewRequest,
    MaterialLibraryCreateRequest,
    MaterialLibraryItemDto,
    MaterialQuickEditRequest,
    MaterialUpdate,
    MaterialUpdateRequest,
    GenerateNextSessionRecommendationsRequest,
    NextSessionRecommendationDto,
    ReviewNextSessionRecommendationRequest,
    CreateNextSessionPlanRequest,
    UpdateNextSessionPlanRequest,
    CreateNextSessionPackageRequest,
    NextSessionMaterialImpactPlanDto,
    SelectiveMaterialRegenerationRequest,
    SelectiveScenarioRegenerationRequest,
    LearnerProgressSummaryDto,
    ProgressDataPointDto,
    ProgressSignalDto,
    RecentLessonDto,
    ProgressObservation,
    ProgressSummary,
    ProgressMetric,
    QuestionAnswerUpdate,
    RecordUploadRequest,
    RecordUploadIntentRequest,
    RecordUploadIntentResponse,
    RecordUploadCompleteRequest,
    RecordTextCorrectionRequest,
    RecordDeletionResponse,
    SessionCreate,
    CompleteSessionRequest,
    SessionCompletionTemplateDto,
    SessionOutcomeDto,
    StartSessionRequest,
    PatchSessionRunDraftRequest,
    CompleteSessionRunDraftRequest,
    DiscardSessionRunDraftRequest,
    SessionRunStateDto,
    SessionDataRecordRequest,
    StartLessonChatRequest,
    UpdateAIQuestionAnswerRequest,
    RefreshLessonRecommendationsRequest,
    PackageContentPlanActionRequest,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_spec_service import V2LessonSpecService
from app.services.v2_instructional_constraint_service import build_instructional_constraint_snapshot
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_generation_job_service import V2GenerationJobService
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_progress_service import V2ProgressService
from app.services.v2_goal_progress_service import V2GoalProgressService
from app.services.v2_next_session_recommendation_service import V2NextSessionRecommendationService
from app.services.v2_next_session_workflow_service import V2NextSessionWorkflowService
from app.services.v2_record_service import V2RecordService
from app.services.v2_repositories import repositories
from app.services.v2_session_service import V2SessionService
from app.services.v2_session_outcome_service import V2SessionOutcomeService
from app.services.v2_session_run_service import V2SessionRunService
from app.services.v2_handoff_export_service import V2HandoffExportService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_print_readiness_service import V2PrintReadinessService
from app.services.v2_print_preset_service import V2PrintPresetService
from app.services.v2_synthetic_n482_fixture_service import (
    V2SyntheticN482FixtureService,
)
from app.integrations.private_object_storage import (
    LocalPrivateObjectStorage,
    PrivateObjectStorage,
    download_content_disposition,
    get_private_object_storage,
)

router = APIRouter(
    prefix="/v2",
    tags=["v2-product"],
    dependencies=[Depends(get_current_teacher)],
)
logger = logging.getLogger(__name__)


def _prepare_package_images_background(
    job_id: str, scope: AuthenticatedScope | None
) -> None:
    token = set_authenticated_scope(scope) if scope is not None else None
    try:
        V2GenerationJobService().resume(job_id)
    except Exception:
        logger.warning(
            "package_image_background_task_failed",
            extra={
                "event": "package_image_background_task_failed",
                "generation_job_id": job_id,
            },
        )
    finally:
        if token is not None:
            reset_authenticated_scope(token)


def _prepare_material_image_background(
    material_id: str, scope: AuthenticatedScope | None
) -> None:
    token = set_authenticated_scope(scope) if scope is not None else None
    try:
        V2LessonPackageService().prepare_material_image(
            material_id, force_generation=True
        )
    except Exception:
        logger.warning(
            "material_image_background_task_failed",
            extra={
                "event": "material_image_background_task_failed",
                "material_id": material_id,
            },
        )
        try:
            V2MaterialService().set_image_generation_status(
                material_id,
                "failed",
                "Artwork could not be generated. Please try again.",
            )
        except Exception:
            logger.warning(
                "material_image_failure_status_not_saved",
                extra={
                    "event": "material_image_failure_status_not_saved",
                    "material_id": material_id,
                },
            )
    finally:
        if token is not None:
            reset_authenticated_scope(token)


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


def _printable_lesson_kit_service(
    current: CurrentTeacher = Depends(get_current_teacher),
) -> V2PrintableLessonKitService:
    return V2PrintableLessonKitService(repositories)


def _print_readiness_service(
    current: CurrentTeacher = Depends(get_current_teacher),
) -> V2PrintReadinessService:
    return V2PrintReadinessService(repositories)


def _print_preset_service(
    current: CurrentTeacher = Depends(get_current_teacher),
) -> V2PrintPresetService:
    return V2PrintPresetService(repositories)


def _synthetic_n482_fixture_service(
    current: CurrentTeacher = Depends(get_current_teacher),
) -> V2SyntheticN482FixtureService:
    return V2SyntheticN482FixtureService(repositories, settings)


def _private_object_storage() -> PrivateObjectStorage:
    return get_private_object_storage(settings)


def _require_development() -> None:
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=404, detail="Not found")


@router.post(
    "/dev/fixtures/n482/reset",
    dependencies=[Depends(_require_development)],
)
def reset_synthetic_n482_fixture(
    service: V2SyntheticN482FixtureService = Depends(
        _synthetic_n482_fixture_service
    ),
) -> dict[str, object]:
    return service.reset()


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
    snapshot = build_instructional_constraint_snapshot(
        learner, V2RecordService().list_for_learner(payload.learnerId)
    )
    lesson_spec = V2LessonSpecService().require_valid(
        V2LessonSpecService().from_draft(draft, learner, snapshot), snapshot
    )
    try:
        generated = provider.generate_lesson_package(lesson_spec)
    except RuntimeError:
        logger.warning(
            "Development OpenAI lesson package request failed; using mock fallback"
        )
        provider = MockV2AIProvider()
        generated = provider.generate_lesson_package(lesson_spec)
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


@router.patch(
    "/learners/{learner_id}/profile-factors/{factor_id}",
    response_model=LearnerProfileDto,
)
def review_profile_factor(
    learner_id: str, factor_id: str, payload: ProfileFactorReviewRequest
) -> LearnerProfileDto:
    return V2LearnerService().review_factor(learner_id, factor_id, payload)


@router.post("/learners/{learner_id}/profile/confirm", response_model=LearnerProfileDto)
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


@router.get(
    "/lesson-chat/{conversation_id}",
    response_model=AIChatStateDto,
)
def get_lesson_chat(conversation_id: str) -> AIChatStateDto:
    """Return the latest persisted draft for optimistic-conflict recovery."""

    return V2LessonChatService().to_dto(V2LessonChatService().get(conversation_id))


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
            expected_draft_version=payload.expectedDraftVersion,
            save_unsupported_for_future=payload.saveUnsupportedForFuture,
        ),
    )


@router.post(
    "/lesson-chat/{conversation_id}/refresh-recommendations",
    response_model=AIChatStateDto,
)
def refresh_lesson_recommendations(
    conversation_id: str, payload: RefreshLessonRecommendationsRequest
) -> AIChatStateDto:
    return V2LessonChatService().to_dto(
        V2LessonChatService().refresh_recommendations(
            conversation_id, payload.expectedDraftVersion
        )
    )


@router.post(
    "/lesson-chat/{conversation_id}/content-plan",
    response_model=AIChatStateDto,
)
def preview_lesson_content_plan(
    conversation_id: str, payload: RefreshLessonRecommendationsRequest
) -> AIChatStateDto:
    return V2LessonChatService().preview_package_content_plan(
        conversation_id, payload.expectedDraftVersion
    )


@router.patch(
    "/lesson-chat/{conversation_id}/content-plan",
    response_model=AIChatStateDto,
)
def adjust_lesson_content_plan(
    conversation_id: str, payload: PackageContentPlanActionRequest
) -> AIChatStateDto:
    return V2LessonChatService().adjust_package_content_plan(conversation_id, payload)


@router.post("/lesson-chat/{conversation_id}/clear", response_model=AIChatStateDto)
def clear_lesson_chat(conversation_id: str) -> AIChatStateDto:
    return V2LessonChatService().clear_dto(conversation_id)


@router.post("/lesson-chat/{conversation_id}/cancel", response_model=AIChatStateDto)
def cancel_lesson_chat_request(conversation_id: str) -> AIChatStateDto:
    return V2LessonChatService().cancel_request_dto(conversation_id)


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
    background_tasks: BackgroundTasks,
) -> LessonPackageDto:
    job_service = V2GenerationJobService()
    job, package = job_service.create_or_resume(draft)
    if settings.AI_PROVIDER != "mock":
        if job_service.claim_visual_work(job.jobId):
            package = job_service.packages.queue_product_images(package.id)
            background_tasks.add_task(
                _prepare_package_images_background,
                job.jobId,
                get_authenticated_scope(),
            )
    elif job.status not in {"completed", "partially_complete"}:
        job_service.resume(job.jobId)
        package = job_service.packages.get_product(package.id)
    return package


@router.post("/lesson-packages", response_model=LessonPackageDto, status_code=201)
def generate_lesson_package(
    draft: LessonDesignDraftDto, background_tasks: BackgroundTasks
) -> LessonPackageDto:
    """Compatibility alias for the initial Backend v2 route."""

    return generate_product_lesson_package(draft, background_tasks)


@router.get("/lesson-packages", response_model=list[LessonPackageDto])
def list_lesson_packages(learnerId: str | None = None) -> list[LessonPackageDto]:
    return V2LessonPackageService().list_products(learnerId)


@router.get("/generation-jobs/{job_id}", response_model=GenerationJobDto)
def get_generation_job(job_id: str) -> GenerationJobDto:
    return V2GenerationJobService().get(job_id)


@router.get(
    "/lesson-packages/{package_id}/generation-job",
    response_model=GenerationJobDto,
)
def get_package_generation_job(package_id: str) -> GenerationJobDto:
    return V2GenerationJobService().for_package(package_id)


@router.post("/generation-jobs/{job_id}/retry", response_model=GenerationJobDto)
def retry_generation_job(job_id: str) -> GenerationJobDto:
    return V2GenerationJobService().resume(job_id)


@router.post(
    "/generation-jobs/{job_id}/visuals/{visual_id}/retry",
    response_model=GenerationJobDto,
)
def retry_generation_visual(job_id: str, visual_id: str) -> GenerationJobDto:
    return V2GenerationJobService().retry_visual(job_id, visual_id)


@router.get("/lesson-packages/{package_id}", response_model=LessonPackageDto)
def get_lesson_package(package_id: str) -> LessonPackageDto:
    return V2LessonPackageService().get_product(package_id)


@router.get(
    "/lesson-packages/{package_id}/print-readiness",
    response_model=PackagePrintReadiness,
)
def get_lesson_package_print_readiness(
    package_id: str,
    service: V2PrintReadinessService = Depends(_print_readiness_service),
) -> PackagePrintReadiness:
    return service.evaluate(package_id)


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


@router.post(
    "/lesson-packages/{package_id}/revalidate",
    response_model=LessonPackageDto,
)
def revalidate_lesson_package(package_id: str) -> LessonPackageDto:
    return V2LessonPackageService().revalidate_product(package_id)


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


@router.post(
    "/lesson-packages/{package_id}/section-edit-preview",
    response_model=LessonSectionEditPreviewDto,
)
def preview_lesson_package_section_edit(
    package_id: str, payload: LessonSectionEditPreviewRequest
) -> LessonSectionEditPreviewDto:
    return V2LessonPackageService().preview_section_edit(package_id, payload)


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
    "/generated-materials/{material_id}/review",
    response_model=GeneratedMaterialDto,
)
def review_generated_material(material_id: str) -> GeneratedMaterialDto:
    return V2MaterialService().review_generated(material_id)


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
    "/generated-materials/{material_id}/generate-image",
    response_model=GeneratedMaterialDto,
)
def generate_material_image(
    material_id: str, background_tasks: BackgroundTasks
) -> GeneratedMaterialDto:
    service = V2MaterialService()
    pending = service.set_image_generation_status(material_id, "pending")
    background_tasks.add_task(
        _prepare_material_image_background,
        material_id,
        get_authenticated_scope(),
    )
    return pending


@router.post(
    "/generated-materials/{material_id}/visuals/{visual_item_id}/regenerate",
    response_model=GeneratedMaterialDto,
)
def regenerate_material_visual(
    material_id: str, visual_item_id: str
) -> GeneratedMaterialDto:
    return V2LessonPackageService().prepare_material_visual(
        material_id, visual_item_id, force_generation=True
    )


@router.post(
    "/generated-materials/{material_id}/visuals/{visual_item_id}/fallback",
    response_model=GeneratedMaterialDto,
)
def use_material_visual_fallback(
    material_id: str, visual_item_id: str
) -> GeneratedMaterialDto:
    return V2MaterialService().choose_visual_fallback(material_id, visual_item_id)


@router.patch(
    "/generated-materials/{material_id}/visuals/{visual_item_id}/asset",
    response_model=GeneratedMaterialDto,
)
def replace_material_visual(
    material_id: str, visual_item_id: str, payload: VisualAssetReplaceRequest
) -> GeneratedMaterialDto:
    return V2MaterialService().replace_visual_asset(
        material_id, visual_item_id, payload.asset_id
    )


@router.post(
    "/generated-materials/{material_id}/visuals/{visual_item_id}/review",
    response_model=GeneratedMaterialDto,
)
def review_material_visual(
    material_id: str, visual_item_id: str, payload: VisualAssetReviewRequest
) -> GeneratedMaterialDto:
    return V2MaterialService().review_visual(
        material_id, visual_item_id, payload.action
    )


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
    "/lesson-packages/{package_id}/printable-kit",
    response_model=LessonPackageExportJobDto,
)
def create_printable_lesson_kit(
    package_id: str,
    payload: PrintableLessonKitRequest,
    service: V2PrintableLessonKitService = Depends(_printable_lesson_kit_service),
) -> LessonPackageExportJobDto:
    return service.create(package_id, payload)


@router.get(
    "/lesson-packages/{package_id}/print-presets",
    response_model=PrintPresetCatalog,
)
def get_print_preset_catalog(
    package_id: str,
    pageSize: Literal["Letter", "A4"] = "Letter",
    textProfile: Literal["standard", "large"] = "standard",
    service: V2PrintPresetService = Depends(_print_preset_service),
) -> PrintPresetCatalog:
    return service.catalog(
        package_id,
        page_size=pageSize,
        text_profile=textProfile,
    )


@router.post(
    "/lesson-packages/{package_id}/pdf-artifacts",
    response_model=PrintableLessonKitArtifactDto,
    status_code=201,
)
def create_printable_lesson_kit_artifact(
    package_id: str,
    payload: PrintableLessonKitRequest,
    service: V2PrintableLessonKitService = Depends(_printable_lesson_kit_service),
) -> PrintableLessonKitArtifactDto:
    return service.create_artifact(package_id, payload)


@router.post(
    "/printable-lesson-kits/{export_id}/download",
    response_model=HandoffExportDownloadDto,
)
def download_printable_lesson_kit(
    export_id: str,
    service: V2PrintableLessonKitService = Depends(_printable_lesson_kit_service),
) -> HandoffExportDownloadDto:
    return service.create_download(export_id)


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


@router.get("/handoff-exports/{export_id}", response_model=LessonPackageExportJobDto)
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


@router.delete("/handoff-exports/{export_id}", response_model=LessonPackageExportJobDto)
def delete_teacher_handoff_export(
    export_id: str,
    service: V2HandoffExportService = Depends(_handoff_export_service),
) -> LessonPackageExportJobDto:
    return service.delete(export_id)


@router.get("/exports/local/{token}", include_in_schema=False)
def local_teacher_handoff_download(
    token: str,
    storage: PrivateObjectStorage = Depends(_private_object_storage),
) -> Response:
    if not isinstance(storage, LocalPrivateObjectStorage):
        raise HTTPException(status_code=404, detail="Not found")
    body, content_type, download_name = storage.read_presigned_get(token)
    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Content-Disposition": download_content_disposition(download_name),
            "Content-Length": str(len(body)),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
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
    "/sessions/{session_id}/start",
    response_model=SessionRunStateDto,
)
def start_session(
    session_id: str, payload: StartSessionRequest
) -> SessionRunStateDto:
    return V2SessionRunService().start(session_id, payload)


@router.get(
    "/sessions/{session_id}/run",
    response_model=SessionRunStateDto,
)
def get_session_run(session_id: str) -> SessionRunStateDto:
    return V2SessionRunService().state(session_id)


@router.patch(
    "/sessions/{session_id}/run-draft",
    response_model=SessionRunStateDto,
)
def patch_session_run_draft(
    session_id: str, payload: PatchSessionRunDraftRequest
) -> SessionRunStateDto:
    return V2SessionRunService().patch(session_id, payload)


@router.post(
    "/sessions/{session_id}/run-draft/complete",
    response_model=SessionOutcomeDto,
    status_code=201,
)
def complete_session_run_draft(
    session_id: str, payload: CompleteSessionRunDraftRequest
) -> SessionOutcomeDto:
    return V2SessionRunService().complete(session_id, payload)


@router.post(
    "/sessions/{session_id}/run-draft/discard",
    response_model=SessionRunStateDto,
)
def discard_session_run_draft(
    session_id: str, payload: DiscardSessionRunDraftRequest
) -> SessionRunStateDto:
    return V2SessionRunService().discard(session_id, payload)


@router.post(
    "/sessions/{session_id}/duplicate", response_model=LessonSessionDto, status_code=201
)
def duplicate_session(session_id: str) -> LessonSessionDto:
    return V2SessionService().duplicate_dto(session_id)


@router.get("/sessions/{session_id}/summary", response_model=LessonSessionSummaryDto)
def get_session_summary(session_id: str) -> LessonSessionSummaryDto:
    return V2SessionService().summary(session_id)


@router.get(
    "/sessions/{session_id}/completion-template",
    response_model=SessionCompletionTemplateDto,
)
def get_session_completion_template(session_id: str) -> SessionCompletionTemplateDto:
    return V2SessionOutcomeService().completion_template(session_id)


@router.post(
    "/sessions/{session_id}/complete",
    response_model=SessionOutcomeDto,
    status_code=201,
)
def complete_session(
    session_id: str, payload: CompleteSessionRequest
) -> SessionOutcomeDto:
    return V2SessionOutcomeService().complete(session_id, payload)


@router.get(
    "/sessions/{session_id}/outcome",
    response_model=SessionOutcomeDto,
)
def get_session_outcome(session_id: str) -> SessionOutcomeDto:
    outcome = V2SessionOutcomeService().for_session(session_id)
    assert outcome is not None
    return outcome


@router.get(
    "/learners/{learner_id}/session-outcomes",
    response_model=list[SessionOutcomeDto],
)
def list_learner_session_outcomes(learner_id: str) -> list[SessionOutcomeDto]:
    return V2SessionOutcomeService().for_learner(learner_id)


@router.get(
    "/learners/{learner_id}/progress-series-options",
    response_model=list[GoalProgressSeriesOption],
)
def list_goal_progress_series_options(
    learner_id: str,
) -> list[GoalProgressSeriesOption]:
    return V2GoalProgressService().series_options(learner_id)


@router.get(
    "/learners/{learner_id}/progress-series",
    response_model=GoalProgressSeries,
)
def get_goal_progress_series(
    learner_id: str,
    goalId: str | None = None,
    goalRevision: int | None = None,
    metric: ProgressMetric = "independent_success_rate",
    contextKey: str | None = None,
) -> GoalProgressSeries:
    return V2GoalProgressService().series(
        learner_id,
        goal_id=goalId,
        goal_revision=goalRevision,
        metric=metric,
        context_key=contextKey,
    )


@router.get(
    "/learners/{learner_id}/next-session-recommendations",
    response_model=list[NextSessionRecommendationDto],
)
def list_next_session_recommendations(
    learner_id: str,
    goalId: str | None = None,
    goalRevision: int | None = None,
) -> list[NextSessionRecommendationDto]:
    return V2NextSessionRecommendationService().list(
        learner_id, goal_id=goalId, goal_revision=goalRevision
    )


@router.post(
    "/learners/{learner_id}/next-session-recommendations/generate",
    response_model=list[NextSessionRecommendationDto],
)
def generate_next_session_recommendations(
    learner_id: str,
    payload: GenerateNextSessionRecommendationsRequest,
) -> list[NextSessionRecommendationDto]:
    return V2NextSessionRecommendationService().generate(
        learner_id, payload.goalId, payload.goalRevision
    )


@router.patch(
    "/next-session-recommendations/{recommendation_id}",
    response_model=NextSessionRecommendationDto,
)
def review_next_session_recommendation(
    recommendation_id: str,
    payload: ReviewNextSessionRecommendationRequest,
) -> NextSessionRecommendationDto:
    return V2NextSessionRecommendationService().review(recommendation_id, payload)


@router.post(
    "/lesson-packages/{package_id}/next-session-plan",
    response_model=NextSessionMaterialImpactPlanDto,
)
def create_next_session_plan(
    package_id: str,
    payload: CreateNextSessionPlanRequest,
) -> NextSessionMaterialImpactPlanDto:
    return V2NextSessionWorkflowService().create_plan(
        package_id, payload.expectedPackageRevision
    )


@router.get(
    "/next-session-plans/{plan_id}",
    response_model=NextSessionMaterialImpactPlanDto,
)
def get_next_session_plan(plan_id: str) -> NextSessionMaterialImpactPlanDto:
    return V2NextSessionWorkflowService().get_plan(plan_id)


@router.patch(
    "/next-session-plans/{plan_id}",
    response_model=NextSessionMaterialImpactPlanDto,
)
def update_next_session_plan(
    plan_id: str,
    payload: UpdateNextSessionPlanRequest,
) -> NextSessionMaterialImpactPlanDto:
    return V2NextSessionWorkflowService().update_plan(plan_id, payload)


@router.post(
    "/next-session-plans/{plan_id}/create-package",
    response_model=LessonPackageDto,
)
def create_next_session_package(
    plan_id: str,
    payload: CreateNextSessionPackageRequest,
) -> LessonPackageDto:
    return V2NextSessionWorkflowService().create_package(
        plan_id, payload.expectedPlanVersion
    )


@router.post(
    "/lesson-packages/{package_id}/materials/{material_id}/regenerate",
    response_model=GeneratedMaterialDto,
)
def regenerate_next_session_material(
    package_id: str,
    material_id: str,
    payload: SelectiveMaterialRegenerationRequest,
) -> GeneratedMaterialDto:
    return V2NextSessionWorkflowService().regenerate_material(
        package_id, material_id, payload.expectedMaterialVersion
    )


@router.post(
    "/lesson-packages/{package_id}/materials/{material_id}/regenerate-scenario",
    response_model=GeneratedMaterialDto,
)
def regenerate_next_session_scenario(
    package_id: str,
    material_id: str,
    payload: SelectiveScenarioRegenerationRequest,
) -> GeneratedMaterialDto:
    return V2NextSessionWorkflowService().regenerate_scenario(
        package_id, material_id, payload
    )


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
