import json
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.schemas.v2_dto import (
    CanonicalLearnerProfile,
    LearnerProfileSummary,
    GoalDecisionValue,
    LearnerProfile,
    LessonDesignDraftDto,
    LessonSpecAssumption,
    MaterialRequestDecisionValue,
    MaterialRequestItem,
    PracticeContextDecisionValue,
    PracticeContextItem,
    ProfileFactor,
    TeacherDecision,
)
from app.services.v2_instructional_constraint_service import build_instructional_constraint_snapshot
from app.services.v2_lesson_spec_service import V2LessonSpecService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories


def factor(fid, category, value, *, status="confirmed_current", constraint=""):
    return ProfileFactor(
        id=fid, category=category, label=fid, value=value, status=status,
        confidence=.99, sourceEvidence="Synthetic N-482 record", sourceRecordId="record-n482",
        instructionalImplication=value,
        generationConstraints=[constraint] if constraint else [],
        teacherReviewed=True,
    )


def n482_learner():
    factors = [
        factor("communication", "communication", "Speech and AAC are accepted equally"),
        factor("wait-five", "prompting", "Wait at least five seconds", constraint="minimum_processing_wait_seconds=5"),
        factor("prompt-sequence", "prompting", "Independent opportunity, visual or gestural cue, model, then brief verbal prompt"),
        factor("no-hoh", "prohibited_item", "Hand-over-hand prompting is prohibited"),
        factor("six-minute", "attention", "Maximum six-minute teaching block", constraint="maximum_teaching_block_minutes=6"),
        factor("five-bus", "reinforcement", "Use a five-token board with bus-icon tokens", constraint="token_count=5"),
        factor("reward", "reinforcement", "Two-minute transit-map reward"),
        factor("praise", "reinforcement", "Specific praise: You asked for a break by yourself."),
        factor("blue-lines", "current_interest", "Blue transit lines"),
        factor("transition", "transition", "Use First–Then, a one-minute visual warning, and present First–Then again on return"),
        factor("break", "regulation", "Honor a two-minute break request with a visible timer", constraint="break_duration_minutes=2"),
        factor("low-clutter", "visual_access", "Use high-contrast low-clutter pages"),
        factor("four-choices", "visual_access", "Use no more than four choices", constraint="maximum_response_options_per_page=4"),
        factor("no-audio", "sensory", "No audio prompts, sound effects, applause, or alarms"),
        factor("no-writing", "motor_access", "Do not require handwriting"),
        factor("no-cutting", "motor_access", "Avoid fine-motor cutting"),
        factor("generalization", "generalization", "Practice across transit-map activity to table work, art activity to cleanup, and free choice to shared reading", constraint="minimum_generalization_contexts=3"),
        factor("spanish", "unresolved_assumption", "Whether paired Spanish labels improve comprehension", status="unconfirmed"),
        factor("illustration", "unresolved_assumption", "Whether photographs or line drawings are preferred", status="unconfirmed"),
        factor("food", "reinforcement", "Food rewards", status="not_approved"),
    ]
    profile = CanonicalLearnerProfile(
        learnerId="n482", age=9, factors=factors,
        confirmedFactorIds=[item.id for item in factors if item.status == "confirmed_current"],
        unconfirmedFactorIds=["spanish", "illustration"],
        historicalFactorIds=[], excludedFactorIds=["food"], blockingIssues=[],
        summary=LearnerProfileSummary(
            communication="Speech and AAC", supports=["First–Then"],
            currentInterests=["Blue transit lines"], learningFormat="Brief visual blocks",
            keyTeachingNotes=["Wait five seconds"],
        ),
    )
    return LearnerProfile(id="n482", code="N-482", age=9, normalizedProfile=profile)


def n482_draft(snapshot):
    goal = TeacherDecision(
        id="decision-goal", field="goal", source="teacher_edited",
        value=GoalDecisionValue(
            teacherRequest='Teach requesting “Break, please” during transitions.',
            interpretedGoal='Independently request “Break, please” using speech or AAC during transitions.',
            observableBehavior='Requests “Break, please” using speech or AAC',
            conditions="During selected transitions", acceptedResponseModes=["speech", "AAC"],
        ),
    )
    labels = [
        "transit-map activity to table work", "art activity to cleanup",
        "free choice to shared reading",
    ]
    contexts = [
        PracticeContextItem(
            id=f"context-{index}", label=label, setting=label,
            transitionFrom=label.split(" to ")[0], transitionTo=label.split(" to ")[1],
            generalizationDimension="activity",
        ) for index, label in enumerate(labels, 1)
    ]
    context_decision = TeacherDecision(
        id="decision-contexts", field="practice_contexts", source="teacher_selected",
        optionIds=[item.id for item in contexts], value=PracticeContextDecisionValue(contexts=contexts),
    )
    requested = [
        ("blue_line_activity", "personalized Blue Line activity", "Practice the goal in a motivating transition context"),
        ("break_card", "Break, Please communication card", "Provide speech and AAC-equivalent communication access"),
        ("first_then_board", "concrete First–Then board", "Preview and support transition completion"),
        ("token_board", "five-bus-token board", "Represent progress toward the confirmed reward"),
        ("visual_timer", "two-minute visual timer", "Show the honored break duration without audio"),
        ("scenario_cards", "transition scenario cards", "Practice across three selected contexts"),
        ("data_sheet", "goal-specific data sheet", "Measure independent break requests and prompting"),
        ("summary_template", "lesson summary", "Document response modes and next steps"),
    ]
    materials = [
        MaterialRequestItem(
            requestId=f"request-{index}", materialType=material_type,
            customLabel=label, purpose=purpose, profileFactorIds=snapshot.profile_factor_ids,
            libraryConfiguration=(
                {
                    "activityTitle": "Complete the Blue Line",
                }
                if material_type == "blue_line_activity"
                else {
                    "firstTask": "Complete 3 table-work items",
                    "thenOutcome": "2-minute transit-map break",
                    "completionCriterion": "Complete all 3 table-work items",
                    "returnSupport": "After the break, check First–Then and return to the next table-work item.",
                }
                if material_type == "first_then_board"
                else {
                    "returnCue": "Break finished — check First–Then",
                }
                if material_type == "visual_timer"
                else None
            ),
        ) for index, (material_type, label, purpose) in enumerate(requested, 1)
    ]
    material_decision = TeacherDecision(
        id="decision-materials", field="material_requests", source="teacher_selected",
        optionIds=[item.request_id for item in materials],
        value=MaterialRequestDecisionValue(materials=materials),
    )
    return LessonDesignDraftDto(
        id="draft-n482", learnerId="n482",
        goalText=goal.value.interpreted_goal, observableResponse=goal.value.observable_behavior,
        responseLevel="speech or AAC", scenarios=labels,
        selectedMaterials=[item.custom_label for item in materials],
        theme="Blue transit lines", duration="25 min", customNotes="", opportunities=5,
        profileRevision=snapshot.profile_revision, instructionalConstraintSnapshot=snapshot,
        teacherRequest=goal.value.teacher_request,
        decisions=[goal, context_decision, material_decision],
    )


@pytest.fixture
def canonical_case():
    learner = n482_learner()
    snapshot = build_instructional_constraint_snapshot(learner, [])
    draft = n482_draft(snapshot)
    service = V2LessonSpecService()
    return service, snapshot, service.from_draft(draft, learner, snapshot)


def issue_codes(report):
    return {item.code for item in report.issues}


def test_plain_language_bus_token_theme_is_preserved():
    assert V2LessonSpecService._token_theme(
        ["Use exactly five bus tokens."]
    ) == "bus"


def test_combined_token_exchange_keeps_reward_duration_out_of_token_count():
    source = ["bus tokens exchanged for two minutes with transit"]

    assert V2LessonSpecService._first_number(source, ("token",)) is None
    assert V2LessonSpecService._token_theme(source) == "bus"
    reward = V2LessonSpecService._reward_after_token_exchange(source)
    assert reward == "two minutes with transit"
    assert V2LessonSpecService._concrete_reward_phrase(reward, 2) == (
        "2 minutes with transit"
    )


def test_explicit_acknowledgment_is_separated_from_prohibited_reward_clause():
    source = [
        "Food rewards are not approved; use specific verbal acknowledgment only."
    ]

    assert V2LessonSpecService._explicit_acknowledgment(source) == (
        "specific verbal acknowledgment"
    )
    assert V2LessonSpecService._excluded_reinforcer_clause(source[0]) == (
        "Food rewards are not approved"
    )


def test_valid_lesson_spec_creation_and_teacher_edit_precedence(canonical_case):
    service, snapshot, spec = canonical_case
    assert service.validate(spec, snapshot).valid
    assert spec.goal.display_text.startswith("Independently request")
    assert spec.provenance.teacher_authored_fields == ["goal"]
    assert [item.label for item in spec.contexts] == [
        "transit-map activity to table work", "art activity to cleanup", "free choice to shared reading"
    ]


def test_stale_profile_revision_rejection(canonical_case):
    service, snapshot, spec = canonical_case
    stale = spec.model_copy(update={"profile_revision": "old-profile"})
    assert "stale_profile_revision" in issue_codes(service.validate(stale, snapshot))


def test_prohibited_reinforcer_and_prompting_rejection(canonical_case):
    service, snapshot, spec = canonical_case
    bad_reward = spec.model_copy(update={
        "reinforcement_plan": spec.reinforcement_plan.model_copy(update={"earned_reward": "Food rewards"})
    })
    assert "prohibited_reinforcer" in issue_codes(service.validate(bad_reward, snapshot))
    bad_prompt = spec.model_copy(update={
        "prompting_plan": spec.prompting_plan.model_copy(update={"sequence": ["Hand-over-hand prompting"]})
    })
    assert "prohibited_prompting" in issue_codes(service.validate(bad_prompt, snapshot))


def test_missing_success_criterion_and_teacher_decisions_rejected(canonical_case):
    service, snapshot, spec = canonical_case
    invalid = spec.model_copy(update={
        "goal": spec.goal.model_copy(update={"success_criterion": None}),
        "decision_ids": [],
    })
    assert {"missing_success_criterion", "missing_teacher_decisions"}.issubset(
        issue_codes(service.validate(invalid, snapshot))
    )
    with pytest.raises(ValidationError) as raised:
        service.require_valid(invalid, snapshot)
    assert raised.value.payload["valid"] is False
    assert raised.value.payload["issues"][0]["fieldPath"]
    assert raised.value.payload["issues"][0]["remediation"]


def test_remaining_constraint_and_contradiction_rules(canonical_case):
    service, snapshot, spec = canonical_case
    first_material = spec.material_requests[0]
    invalid = spec.model_copy(update={
        "goal": spec.goal.model_copy(update={"accepted_response_modes": ["handwriting"]}),
        "communication_plan": spec.communication_plan.model_copy(update={
            "accepted_modes": ["handwriting"], "processing_time_seconds": 5,
        }),
        "prompting_plan": spec.prompting_plan.model_copy(update={"wait_time_seconds": 3}),
        "duration": spec.duration.model_copy(update={"maximum_activity_block_minutes": 7}),
        "contexts": spec.contexts[:1],
        "material_requests": [
            first_material.model_copy(update={"instructional_purpose": ""}),
            *spec.material_requests[1:],
        ],
        "unresolved_assumptions": [LessonSpecAssumption(text="Confirm access method", blocking=True)],
    })
    assert {
        "unsupported_response_method", "contradictory_wait_time",
        "activity_limit_exceeded", "insufficient_generalization_contexts",
        "missing_material_purpose", "blocking_assumption",
    }.issubset(issue_codes(service.validate(invalid, snapshot)))


def test_explicit_default_provenance_and_old_draft_adapter(canonical_case):
    service, snapshot, _ = canonical_case
    learner = n482_learner()
    legacy = LessonDesignDraftDto(
        id="legacy", learnerId="n482", goalText="Requests a break",
        responseLevel="speech", scenarios=["table transition"],
        selectedMaterials=["Break Card"], theme="", duration="", customNotes="",
    )
    spec = service.from_draft(legacy, learner, snapshot)
    assert len(spec.decision_ids) == 3
    assert "duration.totalMinutes" in spec.provenance.defaulted_fields
    resolution = next(item for item in spec.provenance.field_resolutions if item.field_path == "duration.totalMinutes")
    assert resolution.source == "explicit_default"
    assert resolution.requires_teacher_confirmation is True


def test_n482_golden_lesson_spec(canonical_case, tmp_path):
    service, snapshot, spec = canonical_case
    service.require_valid(spec, snapshot)
    assert spec.communication_plan.accepted_modes == ["speech", "AAC"]
    assert spec.communication_plan.processing_time_seconds == 5
    assert spec.prompting_plan.wait_time_seconds == 5
    assert spec.duration.maximum_activity_block_minutes == 6
    assert len(spec.contexts) == 3
    assert any("Hand-over-hand" in item for item in spec.prompting_plan.prohibited_prompts)
    assert spec.reinforcement_plan.token_count == 5
    assert spec.reinforcement_plan.token_theme == "bus"
    assert spec.reinforcement_plan.reward_duration_minutes == 2
    assert spec.reinforcement_plan.earned_reward == "2 minutes with the transit-route map"
    assert spec.reinforcement_plan.specific_praise == "You asked for a break by yourself."
    assert "one-minute visual warning" in spec.transition_plan.warning
    assert spec.transition_plan.break_duration_minutes == 2
    assert spec.access_plan.maximum_primary_visual_choices == 4
    assert any("low-clutter" in item for item in spec.access_plan.layout_requirements)
    assert any("audio" in item.casefold() for item in spec.access_plan.prohibited_audio_features)
    assert any("handwriting" in item.casefold() for item in spec.access_plan.motor_access_alternatives)
    assert any("cutting" in item.casefold() for item in spec.access_plan.motor_access_alternatives)
    assert spec.generalization_plan.required is True
    assert "break_requested" in spec.data_plan.measures
    assert [item.text for item in spec.unresolved_assumptions] == [
        "Whether paired Spanish labels improve comprehension",
        "Whether photographs or line drawings are preferred",
    ]
    assert all(not item.blocking for item in spec.unresolved_assumptions)
    payload = spec.model_dump(mode="json", by_alias=True)
    assert not any(isinstance(item["configuration"], dict) for item in payload["materialRequests"])
    golden_projection = {
        "schemaVersion": payload["schemaVersion"],
        "goal": payload["goal"],
        "duration": payload["duration"],
        "contexts": [item["label"] for item in payload["contexts"]],
        "communicationPlan": payload["communicationPlan"],
        "promptingPlan": payload["promptingPlan"],
        "reinforcementPlan": payload["reinforcementPlan"],
        "transitionPlan": payload["transitionPlan"],
        "accessPlan": payload["accessPlan"],
        "generalizationRequired": payload["generalizationPlan"]["required"],
        "dataMeasures": payload["dataPlan"]["measures"],
        "materialRequests": [
            {key: item[key] for key in ("materialType", "displayLabel", "instructionalPurpose")}
            for item in payload["materialRequests"]
        ],
        "unresolvedAssumptions": payload["unresolvedAssumptions"],
        "decisionIds": payload["decisionIds"],
        "provenance": {
            key: payload["provenance"][key] for key in (
                "teacherAuthoredFields", "teacherSelectedFields",
                "aiRecommendedFields", "derivedFields", "defaultedFields",
            )
        },
    }
    golden_path = Path(__file__).parent / "fixtures" / "n482_lesson_spec_golden.json"
    assert golden_projection == json.loads(golden_path.read_text())


def test_package_provider_and_material_semantics_use_lesson_spec(canonical_case):
    _, snapshot, spec = canonical_case
    repos = V2Repositories()
    learner = n482_learner()
    repos.learners.save(learner)
    service = V2LessonPackageService(repos)
    draft = n482_draft(snapshot)
    draft = draft.model_copy(update={"packageContentPlan": service.preview_content_plan(draft)})
    package = service.generate_product(draft)
    assert package.lessonSpec.id == spec.id
    assert package.lessonSpec.revision == spec.revision
    original_requests = {item.material_type for item in spec.material_requests}
    assert original_requests.issubset({item.material_type for item in package.lessonSpec.material_requests})
    assert package.packageContentPlan is not None
    token = next(item for item in package.materials if item.type == "token_board")
    data = next(item for item in package.materials if item.type == "data_sheet")
    assert token.materialSpec.content.exact_token_count == 5
    assert token.materialSpec.content.token_symbol_or_theme == "bus"
    assert token.materialSpec.content.reward_duration_minutes == 2
    assert data.materialSpec.content.exact_columns == package.lessonSpec.data_plan.measures
    assert {item.type for item in package.materials}.issuperset({"blue_line_activity", "visual_timer"})


def test_provider_rejects_legacy_draft_at_generation_boundary():
    with pytest.raises(TypeError, match="only a validated LessonSpec"):
        V2LessonPackageService(V2Repositories()).ai.generate_lesson_package(
            LessonDesignDraftDto(
                id="legacy-direct", learnerId="n482", goalText="Requests a break",
                responseLevel="speech", theme="", duration="5 minutes", customNotes="",
            )
        )
