import pytest

from app.schemas.v2_dto import LessonDesignDraftDto
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_blueprint_service import V2MaterialBlueprintService
from app.services.v2_repositories import V2Repositories


def _draft(goal: str, *, theme: str = "", scenarios: list[str] | None = None):
    return LessonDesignDraftDto(
        id="draft-material-blueprint",
        learnerId="a102",
        goalText=goal,
        observableResponse=goal,
        responseLevel="Teacher-confirmed accessible response",
        scenarios=scenarios or [],
        selectedMaterials=["Quantity Cards"],
        theme=theme,
        duration="10 minutes",
        customNotes="",
    )


def test_core_goal_families_resolve_to_complete_professional_bundles():
    assert V2MaterialBlueprintService.recommended_bundle(
        _draft("Learner will count quantities from 1 to 5.")
    ) == [
        "quantity_cards",
        "number_cards",
        "matching_page",
        "sorting_page",
        "token_board",
        "data_sheet",
        "summary_template",
    ]
    assert V2MaterialBlueprintService.recommended_bundle(
        _draft("Learner will request help using AAC.")
    ) == [
        "visual_card",
        "help_card",
        "scenario_cards",
        "choice_board",
        "token_board",
        "data_sheet",
        "summary_template",
    ]
    assert V2MaterialBlueprintService.recommended_bundle(
        _draft("Learner will complete a self-care routine and transition.")
    ) == [
        "first_then_board",
        "sequence_cards",
        "choice_board",
        "visual_card",
        "task_analysis_cards",
        "token_board",
        "data_sheet",
        "summary_template",
    ]


def test_material_catalog_defines_professional_construction_rules():
    for material_type in {
        "quantity_cards",
        "number_cards",
        "matching_page",
        "token_board",
        "data_sheet",
        "summary_template",
        "visual_card",
        "help_card",
        "scenario_cards",
        "first_then_board",
        "choice_board",
        "visual_schedule",
        "task_analysis_cards",
        "emotion_scale",
        "sequence_cards",
        "social_narrative",
        "core_word_board",
    }:
        blueprint = V2MaterialBlueprintService.blueprint(material_type)
        assert blueprint is not None
        assert blueprint.instructional_purpose
        assert blueprint.required_content
        assert blueprint.professional_rules
        assert blueprint.teacher_directions


@pytest.mark.parametrize(
    ("goal", "expected_family", "expected_bundle"),
    [
        (
            "Learner will identify a feeling and request a break.",
            "emotional_regulation",
            ["emotion_scale", "break_card", "choice_board", "scenario_cards", "first_then_board", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will follow a two-step direction.",
            "following_directions",
            ["visual_card", "first_then_board", "sequence_cards", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will take turns with a peer during a game.",
            "social_participation",
            ["social_narrative", "scenario_cards", "choice_board", "visual_card", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will complete the classroom arrival routine independently.",
            "routine_independence",
            ["visual_schedule", "task_analysis_cards", "first_then_board", "choice_board", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will use core words to say stop, more, and help.",
            "functional_aac",
            ["core_word_board", "help_card", "choice_board", "scenario_cards", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will match letters to sounds during phonics practice.",
            "early_literacy",
            ["visual_card", "matching_page", "sequence_cards", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will sort classroom objects by category.",
            "concepts_classification",
            ["sorting_page", "matching_page", "visual_card", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will join a familiar play activity.",
            "play_leisure",
            ["choice_board", "scenario_cards", "visual_card", "token_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will follow the community bus safety routine.",
            "community_safety_vocational",
            ["task_analysis_cards", "visual_schedule", "scenario_cards", "help_card", "token_board", "data_sheet", "summary_template"],
        ),
    ],
)
def test_extended_goal_families_resolve_to_complete_bundles(
    goal: str, expected_family: str, expected_bundle: list[str]
):
    draft = _draft(goal)
    assert V2MaterialBlueprintService.classify_goal(draft) == expected_family
    assert V2MaterialBlueprintService.recommended_bundle(draft) == expected_bundle


@pytest.mark.parametrize(
    ("goal", "expected_types"),
    [
        (
            "Learner will complete the classroom arrival routine independently.",
            ["visual_schedule", "task_analysis_cards", "first_then_board", "data_sheet", "summary_template"],
        ),
        (
            "Learner will use core words to say stop, more, and help.",
            ["core_word_board", "help_card", "choice_board", "scenario_cards", "data_sheet"],
        ),
        (
            "Learner will take turns with a peer during a game.",
            ["social_narrative", "scenario_cards", "choice_board", "visual_card", "data_sheet"],
        ),
    ],
)
def test_extended_bundles_generate_typed_materials(
    goal: str, expected_types: list[str]
):
    selected = [
        V2MaterialBlueprintService.blueprint(material_type).display_name
        for material_type in expected_types
    ]
    package = V2LessonPackageService(V2Repositories()).generate_product(
        _draft(goal).model_copy(update={"selectedMaterials": selected})
    )
    assert [material.type for material in package.materials[:5]] == expected_types
    assert all(material.specification is not None for material in package.materials[:5])


def test_counting_package_contains_exact_quantity_and_matching_structures():
    selected = [
        V2MaterialBlueprintService.blueprint(material_type).display_name
        for material_type in (
            "quantity_cards",
            "matching_page",
            "token_board",
            "data_sheet",
            "summary_template",
        )
    ]
    package = V2LessonPackageService(V2Repositories()).generate_product(
        _draft(
            "Learner will count quantities from 1 to 5.",
            theme="Construction vehicles",
            scenarios=["Table practice"],
        ).model_copy(update={"selectedMaterials": selected})
    )

    assert [material.type for material in package.materials] == [
        "quantity_cards",
        "matching_page",
        "token_board",
        "data_sheet",
        "summary_template",
    ]
    quantity_cards = package.materials[0]
    assert quantity_cards.specification is not None
    assert quantity_cards.specification.type == "quantity_cards"
    assert [
        item["quantity"] for item in quantity_cards.content["visualItems"]
    ] == [1, 2, 3, 4, 5]
    assert quantity_cards.specification.professionalRules
