from copy import deepcopy

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.schemas.v2_dto import MaterialUpdateRequest, PrintableLessonKitRequest
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_material_spec_service import V2MaterialSpecService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_repositories import V2Repositories
from test_v2_lesson_spec import (
    build_instructional_constraint_snapshot,
    n482_draft,
    n482_learner,
)


def n482_runtime():
    repos = V2Repositories()
    learner = n482_learner()
    repos.learners.save(learner)
    snapshot = build_instructional_constraint_snapshot(learner, [])
    service = V2LessonPackageService(repos)
    draft = n482_draft(snapshot)
    draft = draft.model_copy(update={"packageContentPlan": service.preview_content_plan(draft)})
    package = service.generate_product(draft)
    return repos, package


@pytest.mark.parametrize(
    "phrase",
    [
        "Practice the target skill",
        "Teacher-confirmed reward",
        "Teacher-confirmed choice",
        "Familiar classroom activity",
        "Specific praise",
        "Selected reinforcer",
        "Add appropriate image",
        "Example item",
        "To be confirmed",
    ],
)
def test_every_listed_placeholder_fails_semantic_validation(phrase):
    _repos, package = n482_runtime()
    summary = next(item.materialSpec for item in package.materials if item.type == "summary_template")
    candidate = summary.model_copy(update={
        "content": summary.content.model_copy(update={"next_step": phrase})
    })

    result = V2MaterialSpecService().validate(candidate, package.lessonSpec)

    assert result.status == "failed"
    assert "placeholder_content" in {item.code for item in result.issues}


def test_material_specific_semantic_failures_have_exact_codes():
    _repos, package = n482_runtime()
    by_type = {item.type: item.materialSpec for item in package.materials}
    token = by_type["token_board"]
    scenario = by_type["scenario_cards"]
    activity = by_type["blue_line_activity"]
    data = by_type["data_sheet"]
    service = V2MaterialSpecService()

    wrong_count = token.model_copy(update={
        "content": token.content.model_copy(update={"exact_token_count": 3})
    })
    prohibited_reward = token.model_copy(update={
        "content": token.content.model_copy(update={"earned_reward": "Food rewards"})
    })
    duplicated = scenario.model_copy(update={
        "content": scenario.content.model_copy(update={
            "scenarios": [
                scenario.content.scenarios[0],
                deepcopy(scenario.content.scenarios[0]),
                scenario.content.scenarios[1],
            ]
        })
    })
    inaccessible = activity.model_copy(update={
        "content": activity.content.model_copy(update={
            "learner_action": "Complete handwriting and cut out each transit card"
        })
    })
    invalid_data = data.model_copy(update={
        "content": data.content.model_copy(update={
            "operationalized_target_behavior": "Sort red shapes",
            "exact_columns": [],
            "independence_rule": "",
            "prompt_level_definitions": [],
        })
    })

    assert "wrong_token_count" in {item.code for item in service.validate(wrong_count, package.lessonSpec).issues}
    assert "prohibited_reinforcer" in {item.code for item in service.validate(prohibited_reward, package.lessonSpec).issues}
    assert "duplicate_scenarios" in {item.code for item in service.validate(duplicated, package.lessonSpec).issues}
    assert "inaccessible_motor_requirement" in {item.code for item in service.validate(inaccessible, package.lessonSpec).issues}
    data_codes = {item.code for item in service.validate(invalid_data, package.lessonSpec).issues}
    assert {"data_sheet_goal_mismatch", "missing_goal_measure", "missing_independence_rule", "missing_prompt_coding"} <= data_codes


def test_bounded_repair_succeeds_without_changing_protected_constraints():
    _repos, package = n482_runtime()
    token = next(item.materialSpec for item in package.materials if item.type == "token_board")
    invalid = token.model_copy(update={
        "content": token.content.model_copy(update={"exact_token_count": 3})
    })
    calls = []

    def repair(current, issues, lesson_spec):
        calls.append([item.code for item in issues])
        return current.model_copy(update={
            "content": current.content.model_copy(update={
                "exact_token_count": lesson_spec.reinforcement_plan.token_count
            }),
            # These application-owned fields must be discarded by the repair boundary.
            "profile_factor_ids": ["ai-invented-factor"],
            "lesson_spec_revision": 999,
        })

    repaired = V2MaterialSpecService().validate_and_repair(invalid, package.lessonSpec, repair)

    assert calls == [["wrong_token_count"]]
    assert repaired.content.exact_token_count == 5
    assert repaired.profile_factor_ids == token.profile_factor_ids
    assert repaired.lesson_spec_revision == package.lessonSpec.revision
    assert repaired.repair_attempts == 1
    assert repaired.repair_status == "repaired"


def test_bounded_repair_exhausts_after_two_attempts_and_fails_closed():
    _repos, package = n482_runtime()
    token = next(item.materialSpec for item in package.materials if item.type == "token_board")
    invalid = token.model_copy(update={
        "content": token.content.model_copy(update={"exact_token_count": 3})
    })
    calls = []

    def no_repair(current, issues, lesson_spec):
        calls.append((current.id, len(issues), lesson_spec.id))
        return current

    with pytest.raises(ValidationError, match="repair exhausted") as error:
        V2MaterialSpecService().validate_and_repair(invalid, package.lessonSpec, no_repair)

    assert len(calls) == 2
    assert error.value.payload["attempts"] == 2
    assert error.value.payload["materialSpec"]["repairStatus"] == "exhausted"


def test_unseen_material_cannot_be_approved_and_edit_invalidates_revision_approval():
    repos, package = n482_runtime()
    service = V2MaterialService(repos)
    token = next(item for item in package.materials if item.type == "token_board")

    with pytest.raises(ConflictError, match="Open and review"):
        service.approve_generated(token.id)

    reviewed = service.review_generated(token.id)
    assert reviewed.materialSpec.approval.reviewed_revision == reviewed.materialSpec.revision
    approved = service.approve_generated(token.id)
    assert approved.materialSpec.approval.approved_revision == approved.materialSpec.revision

    edited = service.update_generated(token.id, MaterialUpdateRequest(
        title=approved.title,
        content={**approved.content, "reward": "Food rewards"},
        printLayout=approved.printLayout,
        expectedVersion=approved.version,
    ))

    assert edited.materialSpec.revision == approved.materialSpec.revision + 1
    assert edited.materialSpec.approval.status == "not_reviewed"
    assert edited.materialSpec.approval.reviewed_revision is None
    assert edited.materialSpec.approval.approved_revision is None
    assert edited.materialSpec.semantic_validation.status == "failed"
    assert edited.materialSpec.safety_validation.status == "failed"
    assert edited.status == "validation_failed"
    refreshed = V2LessonPackageService(repos).get_product(package.id)
    assert refreshed.validationStatus == "failed"
    assert any(issue.material_id == token.id for issue in refreshed.safetyReview.structuredIssues)


def test_approved_generated_material_is_persisted_to_materials_library():
    repos, package = n482_runtime()
    service = V2MaterialService(repos)
    communication = next(
        item for item in package.materials if item.type == "break_card"
    )
    service.review_generated(communication.id)

    approved = service.approve_generated(communication.id)

    library = next(
        item
        for item in service.list_library()
        if item.id == f"generated-{communication.id}"
    )
    assert library.source == "generated"
    assert library.title == approved.title
    assert library.type == "Help Cards"
    assert library.configuration == {
        "materialType": "break_card",
        "generatedMaterialId": approved.id,
        "packageId": package.id,
        "materialRevision": approved.materialSpec.revision,
    }
    assert package.learnerId not in library.model_dump_json()


def test_strict_print_gate_rejects_status_only_approval_without_revision_review():
    repos, package = n482_runtime()
    token = next(item for item in package.materials if item.type == "token_board")
    fake_approved_materials = [
        item.model_copy(update={"status": "approved"}) for item in package.materials
    ]
    fake_approved = next(
        item for item in fake_approved_materials if item.id == token.id
    )
    for material in fake_approved_materials:
        repos.generated_materials.save(material)
    package_with_status_only_approval = package.model_copy(update={
        "status": "approved",
        "materials": fake_approved_materials,
        "validatedRevision": package.version + 1,
    })
    saved_package = repos.lesson_packages.save(package_with_status_only_approval)
    assert saved_package.validatedRevision == saved_package.version

    with pytest.raises(ConflictError, match="current material revision"):
        V2PrintableLessonKitService(repos).create(
            package.id,
            PrintableLessonKitRequest(
                materialIds=[item.id for item in package.materials],
                pageSize="Letter",
                reviewedConfirmation=True,
            ),
        )


def test_historical_schema_zero_material_keeps_original_approval_compatibility():
    repos, package = n482_runtime()
    token = next(item for item in package.materials if item.type == "token_board")
    legacy = token.model_copy(update={
        "materialSchemaVersion": 0,
        "materialSpec": None,
        "status": "teacher_review_needed",
    })
    repos.generated_materials.save(legacy)
    repos.lesson_packages.save(package.model_copy(update={
        "validationPolicy": "legacy_compatibility",
        "materials": [legacy if item.id == token.id else item for item in package.materials],
    }))

    approved = V2MaterialService(repos).approve_generated(token.id)

    assert approved.status == "approved"
    assert approved.materialSchemaVersion == 0
