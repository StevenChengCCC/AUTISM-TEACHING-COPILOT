from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api.v2_routes import _printable_lesson_kit_service, _private_object_storage
from app.integrations.private_object_storage import LocalPrivateObjectStorage
from app.main import app
from app.schemas.v2_dto import (
    LearnerProfile,
    LessonPackageDecisionRequest,
    MaterialRequestDecisionValue,
    MaterialUpdateRequest,
    PrintableLessonKitRequest,
    ProfileConfirmRequest,
    RecordTextCorrectionRequest,
    RecordUploadCompleteRequest,
    RecordUploadIntentRequest,
    SessionCreate,
)
from app.services.v2_document_parser_service import V2DocumentParserService
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_record_service import V2RecordService
from app.services.v2_repositories import V2Repositories
from app.services.v2_session_service import V2SessionService
from app.services.v2_upload_security_service import V2UploadSecurityService
from test_v2_lesson_spec import n482_draft
from test_v2_printable_lesson_kit import _settings
from test_v2_record_upload import DOCX_MIME, _docx
from test_v2_structured_profile_pipeline import _StructuredProvider


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_learner_profile_n482.txt"
CORE_TYPES = {"break_card", "first_then_board", "data_sheet"}
REQUIRED_TYPES = {
    "blue_line_activity",
    "teacher_cue_card",
    "scenario_cards",
    "visual_timer",
    "token_board",
    "summary_template",
}


def _pdf_text(reader: PdfReader) -> str:
    return " ".join(
        "\n".join(page.extract_text() or "" for page in reader.pages).split()
    )


def _upload_review_and_confirm_profile(repos: V2Repositories, tmp_path: Path):
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    repos.learners.save(LearnerProfile(id="n482", code="N-482", age=0))
    records = V2RecordService(
        repos,
        V2UploadSecurityService(config),
        storage,
        V2DocumentParserService(config),
        config,
    )
    source = FIXTURE.read_text(encoding="utf-8")
    body = _docx(source)
    intent = records.create_upload_intent(
        "n482",
        RecordUploadIntentRequest(
            fileName="Synthetic_Learner_Profile_N482.docx",
            contentType=DOCX_MIME,
            sizeBytes=len(body),
        ),
    )
    storage.put_presigned(intent.uploadUrl.rsplit("/", 1)[-1], body, DOCX_MIME)
    extracted = records.complete_upload(
        "n482", intent.record.id, RecordUploadCompleteRequest()
    )
    assert extracted.status == "needs_review"
    assert "2-by-3 AAC grid" in extracted.extractedText
    reviewed = records.save_correction(
        "n482",
        extracted.id,
        RecordTextCorrectionRequest(
            correctedText=extracted.extractedText,
            expectedVersion=extracted.version,
        ),
    )
    assert reviewed.status == "reviewed"
    profile = V2ProfileExtractionService(
        repos, ai=_StructuredProvider()
    ).extract("n482")
    confirmed = V2LearnerService(repos).confirm_profile(
        "n482", ProfileConfirmRequest(expectedVersion=profile.learner.version)
    )
    assert confirmed.profileReviewStatus == "confirmed"
    return config, storage, profile.instructionalConstraintSnapshot


def test_n482_minimal_selection_complete_generation_download_and_persistence(tmp_path):
    repos = V2Repositories()
    config, storage, snapshot = _upload_review_and_confirm_profile(repos, tmp_path)

    # Exercise the short-request interpretation boundary before using the
    # canonical teacher-reviewed decisions for deterministic acceptance checks.
    chat_service = V2LessonChatService(repos)
    chat = chat_service.start("n482")
    understood = chat_service.submit_request(
        chat.conversation_id, "Teach asking for a break during transitions."
    )
    assert understood.draft.teacher_request
    assert understood.questions

    draft = n482_draft(snapshot)
    material_decision = next(
        item for item in draft.decisions if item.field == "material_requests"
    )
    selected = [
        item
        for item in material_decision.value.materials
        if item.material_type in CORE_TYPES
    ]
    material_decision = material_decision.model_copy(
        update={
            "option_ids": [item.request_id for item in selected],
            "value": MaterialRequestDecisionValue(materials=selected),
            "revision": material_decision.revision + 1,
        }
    )
    draft = draft.model_copy(
        update={
            "selectedMaterials": [item.custom_label for item in selected],
            "decisions": [
                item for item in draft.decisions if item.field != "material_requests"
            ]
            + [material_decision],
        }
    )
    packages = V2LessonPackageService(repos)
    plan = packages.preview_content_plan(draft)
    assert {item.material_type for item in plan.teacher_selected_core} == CORE_TYPES
    assert {item.material_type for item in plan.required_companions} == REQUIRED_TYPES
    assert all(item.reason_required for item in plan.required_companions)
    assert all(not item.default_included for item in plan.optional_enrichments)

    package = packages.generate_product(
        draft.model_copy(update={"packageContentPlan": plan})
    )
    assert {item.type for item in package.materials} == CORE_TYPES | REQUIRED_TYPES
    assert len(package.materials) == 9

    packages.prepare_product_images(package.id)
    package = packages.get_product(package.id)
    scenario = next(item for item in package.materials if item.type == "scenario_cards")
    target = scenario.visualAssetPlan.visual_items[0]
    regenerated = packages.prepare_material_visual(
        scenario.id, target.id, force_generation=True
    )
    assert next(
        item for item in regenerated.visualAssetPlan.visual_items if item.id == target.id
    ).design_constraints["fallbackVisible"] is True
    # A failed required visual is never silently approved. The teacher-facing
    # recovery action explicitly selects the visible deterministic fallback,
    # which converts that current visual revision back to a reviewable state.
    regenerated_target = next(
        item for item in regenerated.visualAssetPlan.visual_items
        if item.id == target.id
    )
    if regenerated_target.status == "failed":
        V2MaterialService(repos).choose_visual_fallback(
            regenerated.id, regenerated_target.id
        )
    for generated_material in packages.get_product(package.id).materials:
        if generated_material.visualAssetPlan is None:
            continue
        for visual in generated_material.visualAssetPlan.visual_items:
            if visual.required and visual.status == "failed":
                V2MaterialService(repos).choose_visual_fallback(
                    generated_material.id, visual.id
                )

    materials = V2MaterialService(repos)
    first_then = next(
        item for item in packages.get_product(package.id).materials
        if item.type == "first_then_board"
    )
    teacher_edit = (
        "Teacher edit: Point to the blue First-Then board before returning "
        "to table work."
    )
    edited = materials.update_generated(
        first_then.id,
        MaterialUpdateRequest(
            title=first_then.title,
            content={
                **first_then.content,
                "returnOrTransitionInstruction": teacher_edit,
            },
            printLayout=first_then.printLayout,
            expectedVersion=first_then.version,
        ),
    )
    assert edited.materialSpec.semantic_validation.status == "passed"
    assert edited.materialSpec.safety_validation.status == "passed"

    for material in packages.get_product(package.id).materials:
        reviewed = materials.review_generated(material.id)
        assert reviewed.materialSpec.approval.status == "reviewed"
        approved = materials.approve_generated(material.id)
        assert approved.materialSpec.approval.status == "approved"

    current = packages.get_product(package.id)
    approved_package = packages.approve_product(
        current.id,
        LessonPackageDecisionRequest(
            expectedVersion=current.version,
            reason="N-482 complete-package acceptance",
        ),
    )
    session = V2SessionService(repos).create(
        SessionCreate(
            learnerId="n482", goal=approved_package.goal, status="planned"
        )
    )

    print_service = V2PrintableLessonKitService(repos, storage, config)
    request = PrintableLessonKitRequest(
        materialIds=[item.id for item in approved_package.materials],
        pageSize="Letter",
        reviewedConfirmation=True,
    )
    client = TestClient(app)
    app.dependency_overrides[_printable_lesson_kit_service] = lambda: print_service
    app.dependency_overrides[_private_object_storage] = lambda: storage
    try:
        response = client.post(
            f"/api/v2/lesson-packages/{approved_package.id}/pdf-artifacts",
            json=request.model_dump(mode="json", by_alias=True),
        )
        assert response.status_code == 201
        artifact = response.json()
        download = client.get(urlsplit(artifact["downloadUrl"]).path)
    finally:
        app.dependency_overrides.pop(_printable_lesson_kit_service, None)
        app.dependency_overrides.pop(_private_object_storage, None)

    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")
    assert len(download.content) == artifact["sizeBytes"] > 0
    reader = PdfReader(BytesIO(download.content))
    # Renderer v5 keeps the Standard Classroom Run Sheet to two pages while
    # preserving the complete package inventory.
    assert len(reader.pages) == artifact["pageCount"] == 17
    text = _pdf_text(reader)
    for phrase in (
        "Complete the Blue Line",
        "Break, please",
        "Complete 3 table-work items",
        "2-minute transit-map break",
        "Opportunity Context Response Outcome",
        "Lesson Summary",
        teacher_edit,
    ):
        assert phrase.casefold() in text.casefold()
    assert "<untrusted_record" not in text.casefold()
    assert set(artifact["materialRevisions"]) == {
        item.id for item in approved_package.materials
    }

    # New service instances model page reloads against the persisted repository.
    library = V2MaterialService(repos).list_library()
    generated = [item for item in library if item.source == "generated"]
    assert len(generated) == len(approved_package.materials)
    assert all("n482" not in item.model_dump_json().casefold() for item in generated)
    assert any(item.id == session.id for item in V2SessionService(repos).list())
    reloaded = V2LessonPackageService(repos).get_product(approved_package.id)
    reloaded_first_then = next(
        item for item in reloaded.materials if item.type == "first_then_board"
    )
    assert (
        reloaded_first_then.materialSpec.content.return_or_transition_instruction
        == teacher_edit
    )
