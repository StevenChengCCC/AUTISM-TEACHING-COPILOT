from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from app.core.exceptions import AIInvalidOutputError, ConflictError
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.schemas.v2_dto import (
    CanonicalLearnerProfile,
    LearnerProfile,
    LearnerRecord,
    ProfileExtractionResult,
    ProfileFactor,
    ProfileFactorReviewRequest,
)
from app.services.v2_ai_context_service import build_ai_safe_profile
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_profile_normalization_service import canonicalize_profile
from app.services.v2_instructional_constraint_service import (
    build_instructional_constraint_snapshot,
)
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_learner_profile_n482.txt"
EXPECTED_NORMALIZED = (
    Path(__file__).parent / "fixtures" / "n482_normalized_expected.json"
)


def _factor(
    factor_id: str,
    category: str,
    value: str,
    *,
    status: str = "confirmed_current",
    constraint: str = "",
) -> ProfileFactor:
    return ProfileFactor(
        id=factor_id,
        category=category,
        label=factor_id.replace("-", " ").title(),
        value=value,
        status=status,
        confidence=0.98,
        sourceEvidence=f"Synthetic evidence for {factor_id}.",
        sourceRecordId="record-n482",
        instructionalImplication=value,
        generationConstraints=[constraint] if constraint else [],
        teacherReviewed=False,
    )


def n482_factors() -> list[ProfileFactor]:
    return [
        _factor(
            "spoken-phrases",
            "communication",
            "Uses spontaneous spoken phrases of 2–5 words",
        ),
        _factor(
            "aac-grid",
            "communication",
            "Uses a 2-by-3 AAC grid with Break, Help, Finished, More, Yes, and No",
            constraint="response_options=Break|Help|Finished|More|Yes|No",
        ),
        _factor(
            "equal-modalities",
            "communication",
            "Speech and AAC are equally valid responses",
            constraint="accept_speech_and_aac_equally",
        ),
        _factor(
            "no-repeat",
            "communication",
            "Do not require verbal repetition after successful AAC",
            constraint="never_require_verbal_repeat_after_aac",
        ),
        _factor(
            "pointing",
            "motor_access",
            "Pointing is a valid response",
            constraint="allow_pointing",
        ),
        _factor(
            "wait-five",
            "prompting",
            "Wait at least five seconds before another prompt",
            constraint="minimum_processing_wait_seconds=5",
        ),
        _factor(
            "refusal-communication",
            "communication",
            "Pushing materials away or saying no may communicate refusal, not noncompliance",
        ),
        _factor(
            "one-step", "receptive_language", "Use brief concrete one-step directions"
        ),
        _factor(
            "two-step",
            "receptive_language",
            "Two-step directions require visual sequencing",
        ),
        _factor(
            "matching",
            "learning_strength",
            "Strong matching, sorting, and sequencing skills",
        ),
        _factor(
            "transit-symbols",
            "learning_strength",
            "Responds strongly to route colors, station icons, and transit symbols",
        ),
        _factor(
            "model-practice",
            "receptive_language",
            "Use a short model followed by immediate practice",
        ),
        _factor(
            "no-long-talk",
            "receptive_language",
            "Long verbal explanations are ineffective",
            constraint="avoid_long_verbal_explanations",
        ),
        _factor(
            "limited-generalization",
            "generalization",
            "Generalization across adults, materials, and contexts is limited",
        ),
        _factor(
            "engagement",
            "attention",
            "Sustains engagement for approximately 6–8 minutes",
        ),
        _factor(
            "six-minute-block",
            "attention",
            "Use teaching blocks of six minutes or less",
            constraint="maximum_teaching_block_minutes=6",
        ),
        _factor("visible-endpoint", "visual_access", "Use a visible endpoint"),
        _factor(
            "low-clutter",
            "visual_access",
            "Use high-contrast low-clutter pages; avoid crowded worksheets",
            constraint="use_high_contrast_low_clutter",
        ),
        _factor(
            "four-options",
            "visual_access",
            "Use no more than four response options per page",
            constraint="maximum_response_options_per_page=4",
        ),
        _factor(
            "no-audio",
            "sensory",
            "Avoid sound effects, applause, alarms, and audio prompts",
            constraint="prohibit_audio_prompts",
        ),
        _factor("calm-visual", "sensory", "Use calm spoken delivery and visual cues"),
        _factor("blue-accent", "visual_access", "Use blue as an organizing accent"),
        _factor(
            "literal-images",
            "visual_access",
            "Use literal neutral images; avoid exaggerated red angry faces",
            constraint="avoid_exaggerated_red_angry_faces",
        ),
        _factor(
            "no-handwriting",
            "motor_access",
            "Do not require handwriting",
            constraint="prohibit_required_handwriting",
        ),
        _factor(
            "no-cutting",
            "motor_access",
            "Avoid fine-motor cutting",
            constraint="prohibit_fine_motor_cutting",
        ),
        _factor(
            "access-options",
            "motor_access",
            "Allow pointing, card placement, stamping, or AAC with large touch targets",
        ),
        *[
            _factor(f"interest-{index}", "current_interest", value)
            for index, value in enumerate(
                (
                    "Subway maps",
                    "City bus route maps",
                    "Blue transit lines",
                    "Station symbols",
                    "Route matching",
                    "Arranging stops in order",
                ),
                1,
            )
        ],
        _factor(
            "transit-reward",
            "reinforcement",
            "Two minutes tracing or building a route on a transit map",
        ),
        _factor(
            "five-token",
            "reinforcement",
            "Use a five-token board with bus-icon tokens",
            constraint="token_count=5",
        ),
        _factor(
            "pictured-reward", "reinforcement", "Picture and name the selected reward"
        ),
        _factor(
            "specific-praise",
            "reinforcement",
            "Use specific praise: You asked for a break by yourself.",
        ),
        _factor(
            "transition",
            "transition",
            "Transit activity to table or paper work is the most difficult transition",
        ),
        _factor(
            "first-then",
            "transition",
            "Use First–Then, a one-minute visual warning, and present First–Then again on return",
        ),
        _factor(
            "break",
            "regulation",
            "Support and honor a functional two-minute break request with a visible timer",
            constraint="break_duration_minutes=2",
        ),
        _factor(
            "low-pressure",
            "safety",
            "Do not provoke distress or label leaving as defiance; begin with low-pressure role-play",
            constraint="never_provoke_distress",
        ),
        _factor(
            "prompt-sequence",
            "prompting",
            "Independent opportunity, then visual or gestural cue, model, then brief verbal prompt",
        ),
        _factor(
            "no-hoh",
            "prohibited_item",
            "Hand-over-hand prompting is prohibited",
            constraint="prohibit_hand_over_hand_prompting",
        ),
        _factor(
            "neutral-correction",
            "error_correction",
            "Use neutral correction: Let us try it together; fade promptly",
        ),
        _factor(
            "three-contexts",
            "generalization",
            "Practice across transit-to-table, art-to-cleanup, and free-choice-to-reading contexts",
            constraint="minimum_generalization_contexts=3",
        ),
        _factor(
            "dinosaurs",
            "historical_interest",
            "Dinosaurs are no longer motivating",
            status="historical",
        ),
        _factor(
            "food",
            "reinforcement",
            "Food rewards",
            status="not_approved",
            constraint="prohibit_food_rewards",
        ),
        _factor(
            "tablet-video",
            "reinforcement",
            "Tablet or video as a default reinforcer",
            status="not_approved",
            constraint="prohibit_tablet_video_default_reinforcer",
        ),
        _factor(
            "generic-stars",
            "reinforcement",
            "Generic stars without a pictured reward",
            status="not_meaningful",
        ),
        _factor(
            "spanish-labels",
            "unresolved_assumption",
            "Whether paired Spanish labels improve comprehension",
            status="unconfirmed",
        ),
        _factor(
            "image-style",
            "unresolved_assumption",
            "Whether photographs or line drawings are preferred",
            status="unconfirmed",
        ),
        _factor(
            "break-settings",
            "unresolved_assumption",
            "Whether the same break routine is appropriate in every setting",
            status="unconfirmed",
        ),
    ]


class _StructuredProvider(MockV2AIProvider):
    def __init__(self):
        super().__init__()
        self.profile_extraction_calls = 0

    def extract_profile(self, learner, records):
        self.profile_extraction_calls += 1
        extracted = learner.model_copy(
            update={
                "age": 9,
                "normalized_profile": CanonicalLearnerProfile(
                    learnerId="source-document-code-must-not-win",
                    age=9,
                    factors=n482_factors(),
                ),
            }
        )
        return ProfileExtractionResult(
            learner=extracted, profileSignals=[], unknownFields=[], insights=[]
        )


def _extract():
    repos = V2Repositories()
    repos.learners.save(LearnerProfile(id="internal-n482", code="APP-482", age=0))
    repos.records.save(
        LearnerRecord(
            id="record-n482",
            learnerId="internal-n482",
            fileName="Synthetic_Learner_Profile_N482.docx",
            fileType="DOCX",
            status="reviewed",
            uploadedAt=datetime.now(timezone.utc),
            extractedText=FIXTURE.read_text(),
        )
    )
    result = V2ProfileExtractionService(repos, ai=_StructuredProvider()).extract(
        "internal-n482"
    )
    return repos, result


def test_n482_factors_survive_normalization_repository_and_api_serialization():
    repos, result = _extract()
    stored = repos.learners.get("internal-n482")
    assert stored and stored.normalized_profile
    factors = stored.normalized_profile.factors
    assert len(factors) == len(n482_factors())
    assert stored.normalized_profile.learner_id == "internal-n482"
    assert result.learner.normalizedProfile == stored.normalized_profile
    api = result.model_dump(mode="json", by_alias=True)
    frontend_state = api["learner"]["normalizedProfile"]
    assert frontend_state == json.loads(EXPECTED_NORMALIZED.read_text())
    assert len(frontend_state["factors"]) == len(factors)
    assert frontend_state["summary"]["communication"]
    assert "Subway maps" in frontend_state["summary"]["currentInterests"]


def test_saved_canonical_profile_is_reused_without_a_second_paid_extraction():
    repos = V2Repositories()
    repos.is_durable = True
    repos.learners.save(LearnerProfile(id="cache-case", code="APP-CACHE", age=0))
    repos.records.save(
        LearnerRecord(
            id="record-cache",
            learnerId="cache-case",
            fileName="synthetic-cache-case.txt",
            fileType="TXT",
            status="reviewed",
            uploadedAt=datetime.now(timezone.utc),
            extractedText="Fully synthetic instructional information.",
        )
    )
    provider = _StructuredProvider()
    service = V2ProfileExtractionService(repos, ai=provider)

    first = service.extract("cache-case", force=True)
    second = service.extract("cache-case")

    assert first.learner.normalizedProfile.factors
    assert second.learner.normalizedProfile.factors
    assert provider.profile_extraction_calls == 1


def test_raw_provider_json_validates_without_losing_structured_factors():
    learner = LearnerProfile(id="internal-n482", code="APP-482", age=0)
    raw = (
        _StructuredProvider()
        .extract_profile(learner, [])
        .model_dump(mode="json", by_alias=True)
    )
    parsed = ProfileExtractionResult.model_validate(raw)
    assert len(parsed.learner.normalized_profile.factors) == len(n482_factors())
    assert parsed.learner.normalized_profile.factors[0].source_evidence


def test_n482_machine_readable_acceptance_constraints_and_statuses():
    _, result = _extract()
    learner = result.learner
    factors = learner.normalizedProfile.factors
    constraints = {item for factor in factors for item in factor.generation_constraints}
    statuses = {factor.id: factor.status for factor in factors}
    assert "minimum_processing_wait_seconds=5" in constraints
    assert "prohibit_hand_over_hand_prompting" in constraints
    assert "prohibit_audio_prompts" in constraints
    assert "maximum_response_options_per_page=4" in constraints
    assert "token_count=5" in constraints
    assert statuses["dinosaurs"] == "historical"
    assert statuses["food"] == statuses["tablet-video"] == "not_approved"
    assert statuses["spanish-labels"] == statuses["image-style"] == "unconfirmed"
    assert "no-hoh" in learner.normalizedProfile.excluded_factor_ids
    assert "Dinosaurs are no longer motivating" not in learner.interests
    assert learner.communicationMode
    assert "Subway maps" in learner.interests
    assert any("Hand-over-hand" in item for item in learner.supportNeeds)
    assert (
        "Two minutes tracing or building a route on a transit map"
        in learner.reinforcementPreferences
    )


def test_single_factor_edit_preserves_all_unrelated_factors():
    repos, result = _extract()
    before = result.learner.normalizedProfile.factors
    updated = V2LearnerService(repos).review_factor(
        "internal-n482",
        "spanish-labels",
        ProfileFactorReviewRequest(
            decision="edit",
            editedValue="Paired labels help in reading tasks",
            expectedVersion=result.learner.version,
        ),
    )
    after = updated.normalizedProfile.factors
    assert len(after) == len(before)
    assert next(f for f in after if f.id == "spanish-labels").teacher_reviewed
    assert next(f for f in after if f.id == "image-style").status == "unconfirmed"


def test_non_instructional_identifiers_are_not_normalized_or_sent_downstream():
    unsafe = n482_factors() + [
        _factor("school-name", "other", "School name: Synthetic Academy"),
        _factor("medical-history", "other", "Medical history: synthetic detail"),
        _factor("family-contact", "other", "Family contact: 555-0100"),
    ]
    learner = canonicalize_profile(
        LearnerProfile(
            id="internal-n482",
            code="APP-482",
            age=9,
            normalizedProfile=CanonicalLearnerProfile(
                learnerId="untrusted", age=9, factors=unsafe
            ),
        )
    )
    serialized = learner.normalized_profile.model_dump_json().casefold()
    assert "synthetic academy" not in serialized
    assert "555-0100" not in serialized
    assert "synthetic detail" not in serialized
    context = build_ai_safe_profile(learner)
    assert "dinosaurs" not in str(context["interests"]).casefold()
    assert any(item["status"] == "not_approved" for item in context["profileFactors"])


class _InvalidProvider(MockV2AIProvider):
    def extract_profile(self, learner, records):
        raise AIInvalidOutputError(
            "The learner profile could not be validated; please retry."
        )


def test_invalid_extraction_is_recoverable_and_does_not_save_an_empty_profile():
    repos = V2Repositories()
    original = repos.learners.save(
        LearnerProfile(id="retry-learner", code="APP-RETRY", age=9)
    )
    record = repos.records.save(
        LearnerRecord(
            id="retry-record",
            learnerId="retry-learner",
            fileName="synthetic.txt",
            fileType="TXT",
            status="reviewed",
            uploadedAt=datetime.now(timezone.utc),
            extractedText="Reviewed synthetic text must remain available.",
        )
    )
    with pytest.raises(AIInvalidOutputError, match="retry"):
        V2ProfileExtractionService(repos, ai=_InvalidProvider()).extract(
            "retry-learner"
        )
    stored = repos.learners.get("retry-learner")
    assert stored == original
    assert repos.records.get(record.id).effective_text == record.effective_text


def test_n482_instructional_snapshot_separates_active_excluded_and_unresolved():
    repos, result = _extract()
    learner = repos.learners.get("internal-n482")
    snapshot = build_instructional_constraint_snapshot(
        learner, repos.records.for_learner("internal-n482")
    )
    assert snapshot.communication.accepted_modes == ["speech", "AAC"]
    assert snapshot.communication.response_options == [
        "Break",
        "Help",
        "Finished",
        "More",
        "Yes",
        "No",
    ]
    assert snapshot.communication.processing_time_seconds == 5
    assert snapshot.instruction.activity_duration_minutes == 6
    assert snapshot.instruction.visible_endpoint_required
    assert snapshot.visual_and_sensory_access.maximum_primary_choices == 4
    assert "Subway maps" in snapshot.engagement.current_interests
    assert (
        "Dinosaurs are no longer motivating" in snapshot.engagement.historical_interests
    )
    assert "Food rewards" in snapshot.engagement.not_approved_reinforcers
    assert "Food rewards" not in snapshot.engagement.effective_reinforcers
    assert snapshot.transitions_and_breaks.first_then_required
    assert snapshot.transitions_and_breaks.break_duration_minutes == 2
    assert len(snapshot.generalization.contexts) == 3
    assert snapshot.unresolved_assumptions == [
        "Whether paired Spanish labels improve comprehension",
        "Whether photographs or line drawings are preferred",
        "Whether the same break routine is appropriate in every setting",
    ]
    serialized = snapshot.model_dump_json().casefold()
    assert "app-482" not in serialized
    assert "synthetic_learner_profile_n482.docx" not in serialized
    assert "synthetic evidence" not in serialized
    assert (
        result.instructionalConstraintSnapshot.profile_revision
        == snapshot.profile_revision
    )


class _SnapshotPlanningProvider(MockV2AIProvider):
    def __init__(self):
        super().__init__()
        self.snapshot = None
        self.catalog = None

    def generate_lesson_questions_with_snapshot(
        self, learner, teacher_request, snapshot, supported_material_catalog
    ):
        self.snapshot = snapshot
        self.catalog = supported_material_catalog
        return super().generate_lesson_questions(learner, teacher_request)


def test_planning_receives_snapshot_and_draft_becomes_stale_after_factor_edit():
    repos, extraction = _extract()
    provider = _SnapshotPlanningProvider()
    chat_service = V2LessonChatService(repos, ai=provider)
    chat = chat_service.start("internal-n482")
    planned = chat_service.submit_request(
        chat.conversation_id, "Teach asking for help during table work"
    )
    assert provider.snapshot.communication.processing_time_seconds == 5
    assert provider.snapshot.engagement.historical_interests == [
        "Dinosaurs are no longer motivating"
    ]
    assert provider.catalog
    old_revision = planned.draft.profile_revision
    learner = repos.learners.get("internal-n482")
    V2LearnerService(repos).review_factor(
        "internal-n482",
        "image-style",
        ProfileFactorReviewRequest(
            decision="edit",
            editedValue="Use line drawings",
            expectedVersion=learner.version,
        ),
    )
    stale = chat_service.get(chat.conversation_id)
    assert stale.draft.profile_stale
    assert not stale.can_generate
    assert (
        build_instructional_constraint_snapshot(
            repos.learners.get("internal-n482"),
            repos.records.for_learner("internal-n482"),
        ).profile_revision
        != old_revision
    )
    with pytest.raises(ConflictError, match="changed"):
        V2LessonPackageService(repos).generate_product(
            V2LessonChatService.to_dto(planned).draft
        )


def test_approved_package_retains_original_profile_snapshot_after_revision_change():
    repos, _ = _extract()
    chat_service = V2LessonChatService(repos, ai=MockV2AIProvider())
    chat = chat_service.start("internal-n482")
    planned = chat_service.submit_request(
        chat.conversation_id, "Teach asking for help during table work"
    )
    package_service = V2LessonPackageService(repos, ai=MockV2AIProvider())
    draft = chat_service.to_dto(planned).draft
    draft = draft.model_copy(update={"packageContentPlan": package_service.preview_content_plan(draft)})
    package = package_service.generate_product(draft)
    approved = repos.lesson_packages.save(
        package.model_copy(update={"status": "approved"})
    )
    original_revision = approved.profileRevision
    original_snapshot = approved.instructionalConstraintSnapshot
    learner = repos.learners.get("internal-n482")
    V2LearnerService(repos).review_factor(
        "internal-n482",
        "spanish-labels",
        ProfileFactorReviewRequest(decision="reject", expectedVersion=learner.version),
    )
    historical = package_service.get_product(approved.id)
    assert historical.profileRevision == original_revision
    assert historical.instructionalConstraintSnapshot == original_snapshot
