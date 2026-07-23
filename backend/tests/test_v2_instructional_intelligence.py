from pathlib import Path

import pytest

from app.core.exceptions import ConflictError
from app.evaluation.round5_runner import run
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.schemas.v2_dto import (
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraftDto,
    LessonPackageDecisionRequest,
    LessonPackageUpdateRequest,
    MaterialUpdateRequest,
    ProfileConfirmRequest,
    ProfileExtractionResult,
    ProfileSignal,
    ProfileSignalReviewRequest,
    QuestionAnswerUpdate,
    utc_now,
)
from app.services.v2_ai_context_service import build_lesson_generation_context
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_repositories import V2Repositories


def product_draft(**updates) -> LessonDesignDraftDto:
    values = {
        "id": "round5-draft",
        "learnerId": "a102",
        "goalText": "Learner will ask for help using an established response.",
        "observableResponse": "Requests help using a short phrase or established AAC response",
        "baseline": "Responds after a visual or model prompt",
        "responseLevel": "Short phrase or established AAC response",
        "scenarios": ["Closed box", "Missing puzzle piece"],
        "selectedMaterials": [
            "Visual Card",
            "Choice Board",
            "First-Then Board",
            "Help Card",
            "Break Card",
            "Token Board",
            "Sorting Page",
            "Matching Page",
            "Scenario Cards",
            "Teacher Cue Card",
            "Data Sheet",
            "Session Summary",
            "Handoff Note",
        ],
        "theme": "Age-neutral classroom",
        "duration": "10 min",
        "customNotes": "Preserve communication access and learner choice.",
    }
    values.update(updates)
    return LessonDesignDraftDto.model_validate(values)


def test_profile_skill_preserves_uncertainty_evidence_and_review_history():
    repos = V2Repositories()
    learner = repos.learners.get("a102")
    assert learner is not None
    records = [
        LearnerRecord(
            id="synthetic-record",
            learner_id="a102",
            file_name="synthetic.txt",
            file_type="TXT",
            status="ready",
            uploaded_at=utc_now(),
            extracted_text=(
                "Caregiver report: learner is interested in cars and uses AAC. "
                "Historical record: outdated conflicting information about communication."
            ),
        )
    ]
    result = MockV2AIProvider().extract_profile(learner, records)
    assert result.profile_signals
    assert all(len(signal.evidence.split()) < 30 for signal in result.profile_signals)
    assert all(
        signal.source_record_id == "synthetic-record"
        for signal in result.profile_signals
    )
    assert any(
        signal.evidence_type == "outdated_evidence" for signal in result.profile_signals
    )
    assert "generalization" in result.unknown_fields

    signal = result.profile_signals[0]
    reviewed_learner = learner.model_copy(update={"profile_signals": [signal]})
    repos.learners.save(reviewed_learner)
    service = V2LearnerService(repos)
    current = service.get("a102")
    rejected = service.review_signal(
        "a102",
        signal.id,
        ProfileSignalReviewRequest(decision="reject", expectedVersion=current.version),
    )
    assert rejected.profileSignals[0].teacher_review_state == "rejected"
    confirmed = service.confirm_profile(
        "a102", ProfileConfirmRequest(expectedVersion=rejected.version)
    )
    assert confirmed.profileReviewStatus == "confirmed"
    assert any(
        item.reviewStatus == "confirmed"
        for item in service.list_profile_versions("a102")
    )


def test_rejected_signal_requires_a_new_evidence_fingerprint_to_return():
    learner = V2Repositories().learners.get("a102")
    assert learner is not None
    rejected = ProfileSignal(
        id="signal-old",
        category="interest",
        label="Trains",
        confidence=0.9,
        status="rejected",
        evidence="A brief evidence summary.",
        source_record_id="record-one",
        evidence_fingerprint="record-one:interest:trains:old",
        teacher_review_state="rejected",
    )
    current = learner.model_copy(update={"profile_signals": [rejected]})
    same = rejected.model_copy(
        update={
            "id": "signal-repeat",
            "status": "suggested",
            "teacher_review_state": "pending",
        }
    )
    merged = V2ProfileExtractionService._merge_profile(
        current,
        ProfileExtractionResult(
            learner=current,
            profileSignals=[same],
            unknownFields=[],
            insights=[],
        ),
    )
    assert len(merged.profile_signals) == 1
    assert merged.profile_signals[0].status == "rejected"

    new_evidence = same.model_copy(
        update={
            "id": "signal-new",
            "evidence_fingerprint": "record-one:interest:trains:new",
        }
    )
    merged_with_new = V2ProfileExtractionService._merge_profile(
        current,
        ProfileExtractionResult(
            learner=current,
            profileSignals=[new_evidence],
            unknownFields=[],
            insights=[],
        ),
    )
    assert {item.id for item in merged_with_new.profile_signals} == {
        "signal-old",
        "signal-new",
    }


def test_profile_extraction_repairs_unconfirmed_legacy_age_but_preserves_confirmed_age():
    draft = LearnerProfile(
        id="legacy-draft",
        code="Learner N-OLD",
        age=7,
        profileReviewStatus="draft",
    )
    extracted = draft.model_copy(update={"age": 10})
    corrected = V2ProfileExtractionService._merge_profile(
        draft,
        ProfileExtractionResult(
            learner=extracted,
            profileSignals=[],
            unknownFields=[],
            insights=[],
        ),
    )
    assert corrected.age == 10

    confirmed = draft.model_copy(update={"profile_review_status": "confirmed"})
    preserved = V2ProfileExtractionService._merge_profile(
        confirmed,
        ProfileExtractionResult(
            learner=extracted,
            profileSignals=[],
            unknownFields=[],
            insights=[],
        ),
    )
    assert preserved.age == 7


def test_lesson_planning_questions_are_dynamic_and_require_teacher_confirmation():
    repos = V2Repositories()
    service = V2LessonChatService(repos)
    state = service.submit_request(
        service.start("a102").conversation_id,
        "I want to teach asking for help.",
    )
    fields = {question.field for question in state.questions}
    assert len(state.questions) > 5
    assert {
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
    }.issubset(fields)
    assert state.can_generate is False
    assert all(
        option.description
        for question in state.questions
        for option in question.options
    )

    state = service.update_answer(
        state.conversation_id,
        "target-response",
        QuestionAnswerUpdate(selected_option_ids=["confirm-target"]),
    )
    state = service.update_answer(
        state.conversation_id,
        "baseline",
        QuestionAnswerUpdate(selected_option_ids=["baseline-prompted"]),
    )
    assert state.can_generate is True
    assert state.draft.baseline == "Responds with prompting"


def test_lesson_context_minimizes_identity_and_record_text():
    learner = V2Repositories().learners.get("a102")
    assert learner is not None
    context = build_lesson_generation_context(learner, product_draft())
    serialized = str(context)
    assert learner.id not in serialized
    assert learner.code not in serialized
    assert learner.notes not in serialized
    assert "extractedText" not in serialized

    unreviewed = V2Repositories().learners.get("n501")
    assert unreviewed is not None and unreviewed.profile_review_status == "draft"
    unreviewed_context = build_lesson_generation_context(
        unreviewed, product_draft(learnerId="n501")
    )
    assert unreviewed_context["interests"] == []
    assert unreviewed_context["reinforcementPreferences"] == []


def test_package_is_typed_evaluated_and_versioned_through_teacher_approval():
    repos = V2Repositories()
    service = V2LessonPackageService(repos)
    package = service.generate_product(product_draft())
    assert package.status == "teacher_review_needed"
    assert package.generationMetadata is not None
    assert package.generationMetadata.skillId == "lesson_generation"
    assert package.safetyReview and package.safetyReview.status == "pass"
    assert len(package.standardsChecks) == 13
    assert all(
        check.version == "instructional-quality-v1" for check in package.standardsChecks
    )
    assert all(step.expectedLearnerResponse for step in package.teachingFlow)
    assert all(step.dataToRecord for step in package.teachingFlow)
    assert package.promptingPlan and package.promptingPlan.teacherOverride
    assert (
        package.dataSheetSpecification
        and "prompt_level" in package.dataSheetSpecification.columns
    )
    assert package.teacherAdaptation and package.teacherAdaptation.signsToPause
    assert {
        item.specification.type for item in package.materials if item.specification
    } >= {
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
        "handoff_note",
    }

    approved = service.approve_product(
        package.id, LessonPackageDecisionRequest(expectedVersion=package.version)
    )
    assert approved.status == "approved"
    edited = service.update_product(
        package.id,
        LessonPackageUpdateRequest(
            lessonBrief="Teacher-edited brief.", expectedVersion=approved.version
        ),
    )
    assert edited.status == "teacher_review_needed"
    versions = service.list_product_versions(package.id)
    assert any(item.status == "approved" for item in versions)
    comparison = service.compare_product_versions(
        package.id, approved.version, edited.version
    )
    assert "lessonBrief" in comparison.changedFields
    restored = service.restore_product_version(
        package.id, approved.version, edited.version
    )
    assert restored.lessonBrief == approved.lessonBrief
    assert restored.status == "teacher_review_needed"


def test_unsafe_package_and_material_cannot_be_approved():
    repos = V2Repositories()
    service = V2LessonPackageService(repos)
    package = service.generate_product(
        product_draft(customNotes="Use punishment and forced eye contact after errors.")
    )
    assert package.status == "safety_review_needed"
    assert package.safetyReview and package.safetyReview.status == "blocked"
    with pytest.raises(ConflictError):
        service.approve_product(
            package.id, LessonPackageDecisionRequest(expectedVersion=package.version)
        )
    material = package.materials[0]
    with pytest.raises(ConflictError):
        V2MaterialService(repos).approve_generated(material.id)

    safe_repos = V2Repositories()
    safe_packages = V2LessonPackageService(safe_repos)
    safe_package = safe_packages.generate_product(product_draft(id="edit-safety"))
    edited_package = safe_packages.update_product(
        safe_package.id,
        LessonPackageUpdateRequest(
            lessonBrief="Use punishment after an incorrect response.",
            expectedVersion=safe_package.version,
        ),
    )
    assert edited_package.status == "safety_review_needed"
    with pytest.raises(ConflictError):
        safe_packages.approve_product(
            edited_package.id,
            LessonPackageDecisionRequest(expectedVersion=edited_package.version),
        )

    safe_materials = V2MaterialService(safe_repos)
    material = safe_package.materials[0]
    unsafe_material = safe_materials.update_generated(
        material.id,
        MaterialUpdateRequest(
            title=material.title,
            content={"instruction": "Force the learner to comply."},
            printLayout=material.printLayout,
            expectedVersion=material.version,
        ),
    )
    with pytest.raises(ConflictError):
        safe_materials.approve_generated(unsafe_material.id)


def test_editing_an_approved_material_creates_teacher_review_draft():
    repos = V2Repositories()
    packages = V2LessonPackageService(repos)
    materials = V2MaterialService(repos)
    package = packages.generate_product(product_draft())
    material = materials.approve_generated(package.materials[0].id)
    current_package = packages.get_product(package.id)
    current_package = packages.approve_product(
        package.id,
        LessonPackageDecisionRequest(expectedVersion=current_package.version),
    )
    edited = materials.update_generated(
        material.id,
        MaterialUpdateRequest(
            title="Teacher-edited support",
            content={**material.content, "instruction": "Help, please."},
            printLayout=material.printLayout,
            expectedVersion=material.version,
        ),
    )
    assert edited.status == "teacher_review_needed"
    assert packages.get_product(package.id).status == "teacher_review_needed"
    assert current_package.status == "approved"


def test_round5_regression_dataset_passes_without_provider():
    dataset = Path(__file__).parents[1] / "evaluation" / "round5_cases.json"
    report = run(dataset)
    assert report["providerCalled"] is False
    assert report["total"] == 13
    assert report["failed"] == 0


def test_selected_records_to_teacher_approved_package_end_to_end():
    repos = V2Repositories()
    extraction = V2ProfileExtractionService(repos).extract("a102")
    assert extraction.analyzedRecordCount > 0
    assert extraction.generationMetadata is not None
    assert extraction.generationMetadata.skillId == "learner_profile"

    chat_service = V2LessonChatService(repos)
    chat = chat_service.submit_request(
        chat_service.start("a102").conversation_id,
        "I want to teach asking for help.",
    )
    for question_id, option_id in (
        ("target-response", "confirm-target"),
        ("baseline", "baseline-prompted"),
    ):
        chat = chat_service.update_answer(
            chat.conversation_id,
            question_id,
            QuestionAnswerUpdate(selected_option_ids=[option_id]),
        )
    assert chat.can_generate is True

    draft = LessonDesignDraftDto.model_validate(
        chat.draft.model_dump(mode="json", by_alias=True)
    )
    packages = V2LessonPackageService(repos)
    package = packages.generate_product(draft)
    assert package.status == "teacher_review_needed"
    assert package.safetyReview and package.safetyReview.status == "pass"
    assert not any(item.status == "blocked" for item in package.standardsChecks)
    approved = packages.approve_product(
        package.id, LessonPackageDecisionRequest(expectedVersion=package.version)
    )
    assert approved.status == "approved"
    assert packages.get_product(package.id).status == "approved"
