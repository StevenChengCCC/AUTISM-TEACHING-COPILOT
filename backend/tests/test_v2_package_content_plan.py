import pytest

from app.core.exceptions import ConflictError
from app.schemas.v2_dto import MaterialRequestDecisionValue, QuestionAnswerUpdate
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_package_content_plan_service import V2PackageContentPlanService
from app.services.v2_repositories import V2Repositories
from test_v2_lesson_spec import (
    build_instructional_constraint_snapshot,
    n482_draft,
    n482_learner,
)
from test_v2_teacher_decision_snapshot import planned_chat


def n482_three_selection_case():
    repos = V2Repositories()
    learner = n482_learner()
    repos.learners.save(learner)
    snapshot = build_instructional_constraint_snapshot(learner, [])
    draft = n482_draft(snapshot)
    decision = next(item for item in draft.decisions if item.field == "material_requests")
    selected_types = {"break_card", "first_then_board", "data_sheet"}
    selected = [item for item in decision.value.materials if item.material_type in selected_types]
    revised_decision = decision.model_copy(update={
        "option_ids": [item.request_id for item in selected],
        "value": MaterialRequestDecisionValue(materials=selected),
        "revision": decision.revision + 1,
    })
    draft = draft.model_copy(update={
        "selectedMaterials": [item.custom_label for item in selected],
        "decisions": [item for item in draft.decisions if item.field != "material_requests"] + [revised_decision],
    })
    package_service = V2LessonPackageService(repos)
    lesson_spec = package_service._lesson_spec_for_content_plan(draft)
    plan = package_service.preview_content_plan(draft)
    return repos, draft, lesson_spec, plan


def test_teacher_selections_remain_core_and_companions_are_deterministic():
    _repos, _draft, _spec, first = n482_three_selection_case()
    _repos, _draft, _spec, second = n482_three_selection_case()

    assert {item.material_type for item in first.teacher_selected_core} == {
        "break_card", "first_then_board", "data_sheet"
    }
    assert {item.material_type for item in first.required_companions} == {
        "visual_timer", "scenario_cards", "teacher_cue_card",
        "token_board", "blue_line_activity", "summary_template",
    }
    assert first.model_dump(exclude={"id"}) == second.model_dump(exclude={"id"})
    assert all(item.reason_required for item in first.required_companions)
    summary = next(
        item
        for item in first.required_companions
        if item.material_type == "summary_template"
    )
    assert summary.can_teacher_remove is False
    assert "goal-specific outcomes" in summary.reason_required


def test_optional_enrichment_can_be_removed_and_nonremovable_dependency_is_blocked():
    _repos, _draft, spec, plan = n482_three_selection_case()
    planner = V2PackageContentPlanService()
    optional = plan.optional_enrichments[0]
    enabled = planner.adjust(plan.model_copy(deep=True), action="set_optional", material_type=optional.material_type, included=True)
    disabled = planner.adjust(enabled, action="set_optional", material_type=optional.material_type, included=False)
    assert next(item for item in disabled.optional_enrichments if item.material_type == optional.material_type).default_included is False
    planner.validate(disabled, spec)

    timer = next(item for item in plan.required_companions if item.material_type == "visual_timer")
    assert timer.can_teacher_remove is False
    with pytest.raises(ConflictError, match="cannot be removed"):
        planner.adjust(plan, action="set_companion", material_type="visual_timer", included=False)


def test_prohibited_or_unsupported_material_is_explicitly_excluded():
    _repos, _draft, spec, _plan = n482_three_selection_case()
    source = spec.material_requests[0]
    unsupported = source.model_copy(update={
        "request_id": "unsupported-scented-spinner",
        "material_type": "scented_holographic_spinner",
        "display_label": "Scented holographic spinner",
        "supported": False,
        "required": False,
        "unsupported_reason": "Not supported and conflicts with the confirmed sensory-access plan.",
        "origin": "future_unsupported",
    })
    spec = spec.model_copy(update={"material_requests": [*spec.material_requests, unsupported]})
    plan = V2PackageContentPlanService().build(spec)

    assert plan.excluded_materials[0].material_type == "scented_holographic_spinner"
    assert "sensory-access" in plan.excluded_materials[0].reason_excluded
    assert "scented_holographic_spinner" not in V2PackageContentPlanService().included_types(plan)


def test_n482_plan_and_generated_package_are_complete_and_within_configured_bounds():
    repos, draft, _spec, plan = n482_three_selection_case()
    assert 6 <= plan.estimated_artifact_count <= 10
    assert 8 <= plan.estimated_page_count <= 16
    draft = draft.model_copy(update={"packageContentPlan": plan})

    package = V2LessonPackageService(repos).generate_product(draft)

    assert package.packageContentPlan == plan
    assert {item.type for item in package.materials} >= {
        "break_card", "first_then_board", "data_sheet", "visual_timer",
        "scenario_cards", "teacher_cue_card", "token_board", "blue_line_activity",
        "summary_template",
    }
    activity = next(
        item.materialSpec for item in package.materials
        if item.type == "blue_line_activity"
    )
    assert activity.title == "Complete the Blue Line"


def test_generation_inventory_equals_core_companions_and_enabled_optionals():
    repos, draft, _spec, plan = n482_three_selection_case()
    optional = plan.optional_enrichments[0]
    plan = V2PackageContentPlanService().adjust(
        plan, action="set_optional", material_type=optional.material_type, included=True
    )
    draft = draft.model_copy(update={"packageContentPlan": plan})

    package = V2LessonPackageService(repos).generate_product(draft)

    assert {item.type for item in package.materials} == V2PackageContentPlanService().included_types(plan)


def test_content_plan_persists_on_resume_and_refresh_preserves_decisions():
    repos = V2Repositories()
    chat_service, chat = planned_chat(repos)
    for field in ("goalText", "scenarios", "selectedMaterials"):
        question = next(item for item in chat.questions if item.field == field)
        selected = (
            question.selected_option_ids[:3]
            if field == "selectedMaterials" and question.selected_option_ids
            else question.selected_option_ids or [question.options[0].id]
        )
        chat = chat_service.update_answer(
            chat.conversation_id,
            question.id,
            QuestionAnswerUpdate(
                selectedOptionIds=selected,
                expectedDraftVersion=chat.draft.version,
            ),
        )
    planned = chat_service.preview_package_content_plan(
        chat.conversation_id, chat.draft.version
    )
    plan = planned.draft.packageContentPlan
    decisions = [item.model_dump(mode="json") for item in planned.draft.decisions]

    resumed = chat_service.start("a102", resume_existing=True)
    assert resumed.draft.package_content_plan == plan

    refreshed = chat_service.refresh_recommendations(
        planned.conversationId, resumed.draft.version
    )
    assert [item.model_dump(mode="json") for item in refreshed.draft.decisions] == decisions
    assert refreshed.draft.package_content_plan == plan
