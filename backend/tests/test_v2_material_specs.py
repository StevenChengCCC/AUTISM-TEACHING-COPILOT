from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError as PydanticValidationError

from app.schemas.v2_dto import (
    ChoiceBoardChoice,
    ChoiceBoardContent,
    ChoiceBoardSpec,
    CommunicationCardContent,
    CommunicationCardSpec,
    FirstThenBoardContent,
    FirstThenBoardSpec,
    GoalSpecificDataSheetContent,
    GoalSpecificDataSheetSpec,
    LessonSummaryContent,
    LessonSummarySpec,
    MaterialDesignConstraints,
    MaterialSpec,
    PersonalizedInstructionalActivityContent,
    PersonalizedInstructionalActivitySpec,
    RegulationScaleContent,
    RegulationScaleLevel,
    RegulationScaleSpec,
    ScenarioCardItem,
    ScenarioCardsContent,
    ScenarioCardsSpec,
    TokenBoardContent,
    TokenBoardSpec,
    VisualTimerContent,
    VisualTimerSpec,
)
from app.services.v2_material_spec_service import V2MaterialSpecService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories
from test_v2_lesson_spec import (
    build_instructional_constraint_snapshot,
    n482_draft,
    n482_learner,
)


def common(artifact_type: str) -> dict:
    return {
        "id": f"material-{artifact_type}",
        "schemaVersion": 1,
        "revision": 1,
        "packageId": "package-1",
        "lessonSpecId": "lesson-spec-1",
        "lessonSpecRevision": 1,
        "learnerId": "learner-1",
        "artifactType": artifact_type,
        "title": artifact_type.replace("_", " ").title(),
        "instructionalPurpose": "Practice the observable goal.",
        "profileFactorIds": ["factor-1"],
        "decisionIds": ["decision-1"],
        "designConstraints": MaterialDesignConstraints(),
        "teacherEditableFields": ["content"],
    }


def valid_specs():
    scenario = ScenarioCardItem(
        id="scenario-1", context="Art to cleanup", triggerOrTransition="Art ends",
        learnerOpportunity="Request a break", expectedResponse="Break, please",
        acceptedModalities=["speech", "AAC"], promptSequence=["visual cue"],
        consequenceOrReinforcement="Honor the break", generalizationDimension="activity",
        visualCue="Show the First–Then board", teacherWording="Cleanup is next. You can request a break.",
        waitTimeSeconds=5, breakOutcome="Honor a two-minute break", returnSupport="Check First–Then",
        generalizationLabel="Generalization: activity",
    )
    return [
        PersonalizedInstructionalActivitySpec(**common("personalized_instructional_activity"), content=PersonalizedInstructionalActivityContent(
            taskName="Sort Blue Line stops", instructionalObjective="Request a break during transitions",
            learnerAction="Place each stop then request a break", teacherSetup=["Arrange three stop cards"],
            requiredComponents=["stop cards"], responseMethod=["speech", "AAC"],
            numberOfTrialsOrItems=3, completionCriterion="Complete 2 of 3 independently",
            answerKeyOrExpectedSequence=["Stop 1", "Stop 2", "Stop 3"],
            generalizationExtension="Repeat during cleanup", motorAccessRequirements=["No cutting"],
            visualAccessRequirements=["Low clutter"],
        )),
        CommunicationCardSpec(**common("communication_card"), content=CommunicationCardContent(
            exactCommunicationPhrase="Break, please", acceptedCommunicationModes=["speech", "AAC"],
            cardPurpose="Request a break", symbolDescription="Pause symbol", alternateText="Break, please card",
            touchTargetRequirement="At least 2 inches", prohibitedImagery=["clutter"],
            teacherResponseAfterUse="Honor the break",
        )),
        FirstThenBoardSpec(**common("first_then_board"), content=FirstThenBoardContent(
            firstTask="Put art supplies in the bin", thenOutcome="Two-minute transit-map break",
            exactDisplayText="FIRST cleanup — THEN map break", firstSymbolDescription="Art bin",
            thenSymbolDescription="Transit map", completionCriterion="Supplies are in the bin",
            context="Art to cleanup", returnOrTransitionInstruction="Show the return cue after two minutes",
        )),
        TokenBoardSpec(**common("token_board"), content=TokenBoardContent(
            exactTokenCount=5, tokenSymbolOrTheme="bus", earnedReward="Transit-map break",
            rewardDurationMinutes=2, picturedRewardDescription="Transit map", specificPraise="You asked clearly",
            deliveryInstructions="Deliver one token after each target response", prohibitedRewardSubstitutions=["food"],
        )),
        VisualTimerSpec(**common("visual_timer"), content=VisualTimerContent(
            durationMinutes=2, startLabel="Break starts", endLabel="Break finished",
            displayFormat="Silent visual countdown", teacherInstruction="Start after the request",
            audioAllowed=False, returnToTaskCue="Show First–Then again",
        )),
        ScenarioCardsSpec(**common("scenario_cards"), content=ScenarioCardsContent(scenarios=[scenario])),
        ChoiceBoardSpec(**common("choice_board"), content=ChoiceBoardContent(
            promptOrQuestion="Choose the next activity", choices=[
                ChoiceBoardChoice(id="one", label="Art", visualDescription="Art supplies"),
                ChoiceBoardChoice(id="two", label="Reading", visualDescription="Book"),
            ], responseMethod=["point", "AAC"], teacherActionAfterSelection="Provide the selected activity",
        )),
        RegulationScaleSpec(**common("regulation_scale"), content=RegulationScaleContent(
            levels=[
                RegulationScaleLevel(order=1, label="Ready", observableIndicators=["Available"], matchingSupportOption="Continue"),
                RegulationScaleLevel(order=2, label="Need support", observableIndicators=["Requests help"], matchingSupportOption="Offer help"),
                RegulationScaleLevel(order=3, label="Need break", observableIndicators=["Requests break"], matchingSupportOption="Honor break"),
            ], nonjudgmentalLanguage="Every level communicates a need.",
        )),
        GoalSpecificDataSheetSpec(**common("goal_specific_data_sheet"), content=GoalSpecificDataSheetContent(
            operationalizedTargetBehavior="Requests Break, please using speech or AAC", trialDefinition="One transition",
            exactColumns=["context", "response_mode", "independence"], responseCoding=["successful", "prompted"],
            promptLevelDefinitions=["independent", "visual"], independenceRule="No prompt after five seconds",
            summaryCalculationsOrTotals=["Independent percentage"],
        )),
        LessonSummarySpec(**common("lesson_summary"), content=LessonSummaryContent(
            goal="Request a break during transitions", observableTarget="Says or selects Break, please",
            contextsPracticed=["Art to cleanup"], responseModesUsed=["speech", "AAC"],
            opportunityTotal=5, successfulOpportunityTotal=4, independenceSummary="Four independent requests",
            promptsUsed=["visual"], reinforcementDelivered="Transit-map break",
            regulationAndBreakNotes="Breaks honored", nextStep="Practice in reading transition",
            reportingFields=["Independent requests", "Teacher notes"],
        )),
    ]


@pytest.mark.parametrize("material_spec", valid_specs(), ids=lambda value: value.artifact_type)
def test_each_material_subtype_round_trips_through_discriminated_union(material_spec):
    payload = material_spec.model_dump(mode="json", by_alias=True)
    parsed = TypeAdapter(MaterialSpec).validate_python(payload)
    assert type(parsed) is type(material_spec)
    assert parsed.schema_version == 1
    assert parsed.profile_factor_ids == ["factor-1"]


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (CommunicationCardContent, {"acceptedCommunicationModes": ["speech"]}),
        (TokenBoardContent, {"exactTokenCount": 5, "tokenSymbolOrTheme": "bus"}),
        (GoalSpecificDataSheetContent, {"operationalizedTargetBehavior": "Requests help"}),
    ],
)
def test_missing_required_semantic_content_is_rejected(model, payload):
    with pytest.raises(PydanticValidationError):
        model.model_validate(payload)


def test_invalid_choice_and_regulation_scale_counts_are_rejected():
    with pytest.raises(PydanticValidationError):
        ChoiceBoardContent(
            promptOrQuestion="Choose", choices=[ChoiceBoardChoice(id="one", label="Only", visualDescription="One")],
            responseMethod=["point"], teacherActionAfterSelection="Provide it",
        )
    with pytest.raises(PydanticValidationError):
        RegulationScaleContent(
            levels=[
                RegulationScaleLevel(order=1, label="One", observableIndicators=["A"], matchingSupportOption="A"),
                RegulationScaleLevel(order=2, label="Two", observableIndicators=["B"], matchingSupportOption="B"),
            ], nonjudgmentalLanguage="Neutral",
        )


def test_placeholders_duplicate_scenarios_and_empty_tasks_are_rejected():
    with pytest.raises(PydanticValidationError, match="concrete"):
        FirstThenBoardContent(
            firstTask="Practice the target skill", thenOutcome="Teacher-confirmed choice",
            exactDisplayText="FIRST practice THEN choice", firstSymbolDescription="first", thenSymbolDescription="then",
            completionCriterion="done", context="classroom", returnOrTransitionInstruction="return",
        )
    with pytest.raises(PydanticValidationError, match="exact communication phrase"):
        CommunicationCardContent(
            exactCommunicationPhrase="To be confirmed", acceptedCommunicationModes=["AAC"], cardPurpose="request",
            symbolDescription="symbol", alternateText="alt", touchTargetRequirement="large",
            teacherResponseAfterUse="respond",
        )
    scenario = valid_specs()[5].content.scenarios[0]
    with pytest.raises(PydanticValidationError, match="distinct"):
        ScenarioCardsContent(scenarios=[scenario, deepcopy(scenario)])
    with pytest.raises(PydanticValidationError, match="executable"):
        PersonalizedInstructionalActivityContent(
            taskName="Activity", instructionalObjective="Practice", learnerAction="Practice the target skill",
            teacherSetup=["setup"], requiredComponents=["item"], responseMethod=["speech"],
            numberOfTrialsOrItems=1, completionCriterion="done", generalizationExtension="repeat",
        )


def n482_package_and_spec():
    repos = V2Repositories()
    learner = n482_learner()
    repos.learners.save(learner)
    snapshot = build_instructional_constraint_snapshot(learner, [])
    service = V2LessonPackageService(repos)
    draft = n482_draft(snapshot)
    draft = draft.model_copy(update={"packageContentPlan": service.preview_content_plan(draft)})
    package = service.generate_product(draft)
    return package, package.lessonSpec


def test_cross_spec_validation_rejects_wrong_token_count_and_unrelated_data_sheet():
    package, lesson_spec = n482_package_and_spec()
    token = next(item.materialSpec for item in package.materials if item.type == "token_board")
    data = next(item.materialSpec for item in package.materials if item.type == "data_sheet")
    wrong_token = token.model_copy(update={
        "content": token.content.model_copy(update={"exact_token_count": 3})
    })
    unrelated_data = data.model_copy(update={
        "content": data.content.model_copy(update={"operationalized_target_behavior": "Sort red shapes"})
    })
    service = V2MaterialSpecService()
    assert service.validate(wrong_token, lesson_spec).issues[0].code == "wrong_token_count"
    assert service.validate(unrelated_data, lesson_spec).issues[0].code == "data_sheet_goal_mismatch"


def test_profile_provenance_is_required():
    payload = valid_specs()[1].model_dump(mode="json", by_alias=True)
    payload["profileFactorIds"] = []
    with pytest.raises(PydanticValidationError):
        TypeAdapter(MaterialSpec).validate_python(payload)


def test_n482_material_specs_and_legacy_adapter():
    package, lesson_spec = n482_package_and_spec()
    expected = {
        "blue_line_activity": "personalized_instructional_activity",
        "break_card": "communication_card",
        "first_then_board": "first_then_board",
        "token_board": "token_board",
        "visual_timer": "visual_timer",
        "scenario_cards": "scenario_cards",
        "data_sheet": "goal_specific_data_sheet",
        "summary_template": "lesson_summary",
    }
    for material_type, artifact_type in expected.items():
        material = next(item for item in package.materials if item.type == material_type)
        assert material.materialSchemaVersion == 1
        assert material.materialSpec.artifact_type == artifact_type
        assert material.materialSpec.semantic_validation.status == "passed"
    scenario_spec = next(item.materialSpec for item in package.materials if item.type == "scenario_cards")
    assert len(scenario_spec.content.scenarios) == 3
    token_spec = next(item.materialSpec for item in package.materials if item.type == "token_board")
    assert token_spec.content.exact_token_count == 5
    assert token_spec.content.token_symbol_or_theme == "bus"

    legacy = next(item for item in package.materials if item.type == "break_card").model_copy(
        update={"materialSchemaVersion": 0, "materialSpec": None}
    )
    adapted = V2MaterialSpecService().adapt_legacy(legacy, lesson_spec)
    assert adapted.materialSchemaVersion == 1
    assert isinstance(adapted.materialSpec, CommunicationCardSpec)
