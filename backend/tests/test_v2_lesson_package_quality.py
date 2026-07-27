from app.schemas.v2_dto import LessonDesignDraftDto
from app.services.v2_lesson_package_quality_service import (
    V2LessonPackageQualityService,
)
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories


def _confirmed_draft() -> LessonDesignDraftDto:
    return LessonDesignDraftDto(
        id="draft-quality-a102",
        learnerId="a102",
        goalText="Learner will ask for help using a short phrase.",
        observableResponse="Learner asks for help using a short phrase or AAC.",
        baseline="Uses a help request in 1 of 5 opportunities with prompts.",
        responseLevel="Short phrase or AAC",
        scenarios=["Toy car stuck", "Closed box"],
        selectedMaterials=[
            "Visual Cards",
            "Help Card",
            "Token Board",
            "Data Sheet",
            "Summary Template",
        ],
        theme="Vehicles",
        duration="10 minutes",
        customNotes="Honor AAC, gesture, or spoken responses.",
        opportunities=5,
    )


def test_generated_package_has_exactly_eight_bounded_quality_scores():
    package = V2LessonPackageService(V2Repositories()).generate_product(
        _confirmed_draft()
    )

    assert package.qualityScore is not None
    assert package.qualityScore.maxScore == 16
    assert len(package.qualityScore.items) == 8
    assert {item.id for item in package.qualityScore.items} == {
        "observable-measurable-goal",
        "complete-material-kit",
        "accurate-teaching-steps",
        "communication-access",
        "image-text-alignment",
        "dignity-choice-sensory",
        "goal-aligned-data-sheet",
        "low-prep-usability",
    }
    assert all(0 <= item.score <= 2 for item in package.qualityScore.items)
    assert package.qualityScore.totalScore == sum(
        item.score for item in package.qualityScore.items
    )
    assert package.qualityScore.teacherReviewRequired is True


def test_missing_materials_and_data_block_quality_approval():
    draft = _confirmed_draft()
    package = V2LessonPackageService(V2Repositories()).generate_product(draft)
    incomplete = package.model_copy(
        update={
            "materials": [],
            "dataSheetSpecification": None,
        }
    )

    result = V2LessonPackageQualityService().evaluate(draft, incomplete)

    assert result.overallStatus == "blocked"
    scores = {item.id: item.score for item in result.items}
    assert scores["complete-material-kit"] == 0
    assert scores["goal-aligned-data-sheet"] == 0
