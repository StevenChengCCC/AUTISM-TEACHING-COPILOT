from copy import deepcopy
import base64

import pytest
from reportlab.graphics import renderSVG

from app.core.exceptions import ConflictError
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_visual_asset_plan_service import V2VisualAssetPlanService
from test_v2_material_specs import valid_specs
from test_v2_semantic_revision import n482_runtime


def by_artifact():
    return {item.artifact_type: item for item in valid_specs()}


def test_visual_count_is_derived_from_personalized_activity_components():
    spec = by_artifact()["personalized_instructional_activity"]
    plan = V2VisualAssetPlanService().build(spec)

    assert len(plan.visual_items) == 6
    assert [item.semantic_key for item in plan.visual_items[:3]] == [
        "route-background", "start-marker", "finish-marker",
    ]
    assert len([item for item in plan.visual_items if item.semantic_key.startswith("station:")]) == 3


def test_three_scenarios_produce_three_distinct_semantic_visuals():
    spec = by_artifact()["scenario_cards"]
    original = spec.content.scenarios[0]
    scenarios = [
        original.model_copy(update={
            "id": f"scenario-{index}",
            "context": context,
            "trigger_or_transition": transition,
        })
        for index, (context, transition) in enumerate([
            ("Transit activity", "Transit activity to table work"),
            ("Art", "Art to cleanup"),
            ("Free choice", "Free choice to shared reading"),
        ], 1)
    ]
    spec = spec.model_copy(update={
        "content": spec.content.model_copy(update={"scenarios": scenarios})
    })

    plan = V2VisualAssetPlanService().build(spec)

    assert len(plan.visual_items) == 3
    assert len({item.semantic_key for item in plan.visual_items}) == 3
    assert all(item.role == "scenario" for item in plan.visual_items)
    assert all(item.design_constraints["context"] in item.prompt for item in plan.visual_items)


def test_choice_count_matches_visual_count_and_first_then_has_two_roles():
    specs = by_artifact()
    choices = specs["choice_board"]
    choice_plan = V2VisualAssetPlanService().build(choices)
    first_then_plan = V2VisualAssetPlanService().build(specs["first_then_board"])

    assert len(choice_plan.visual_items) == len(choices.content.choices)
    assert [item.visible_label for item in choice_plan.visual_items] == [
        item.label for item in choices.content.choices
    ]
    assert [item.role for item in first_then_plan.visual_items] == ["first", "then"]
    assert first_then_plan.visual_items[0].visible_label == specs["first_then_board"].content.first_task
    assert first_then_plan.visual_items[1].visible_label == specs["first_then_board"].content.then_outcome


def test_token_plan_renders_exact_instances_from_one_master_and_one_reward():
    token = by_artifact()["token_board"]
    plan = V2VisualAssetPlanService().build(token)

    masters = [item for item in plan.visual_items if item.semantic_key == "token-symbol"]
    instances = [item for item in plan.visual_items if item.semantic_key.startswith("token-instance:")]
    rewards = [item for item in plan.visual_items if item.role == "reward"]
    assert len(masters) == 1
    assert len(instances) == token.content.exact_token_count
    assert len(rewards) == 1
    assert masters[0].generation_method == "ai_generated"
    assert all(item.generation_method == "deterministic_svg" for item in instances)
    assert all(item.design_constraints["reusesTokenSemanticKey"] == "token-symbol" for item in instances)


def test_failed_required_ai_visual_still_requires_teacher_recovery():
    communication = by_artifact()["communication_card"]
    service = V2VisualAssetPlanService()
    plan = service.build(communication)
    failed = plan.visual_items[0].model_copy(update={
        "status": "failed", "asset_id": plan.visual_items[0].fallback_asset_id,
    })
    plan = plan.model_copy(update={"visual_items": [failed]})

    assert service.approval_blockers(plan) == [
        "Break, please: required visual failed and requires teacher recovery"
    ]
    projected = service.to_renderer_items(plan)[0]
    assert projected["imageUrl"].startswith("data:image/svg+xml;base64,")
    assert projected["generationStatus"] == "ready"


def test_failed_optional_ai_visual_uses_visible_deterministic_fallback():
    communication = by_artifact()["communication_card"]
    service = V2VisualAssetPlanService()
    plan = service.build(communication)
    failed = plan.visual_items[0].model_copy(update={
        "required": False,
        "status": "failed",
        "asset_id": plan.visual_items[0].fallback_asset_id,
    })
    plan = plan.model_copy(update={"visual_items": [failed]})

    assert service.approval_blockers(plan) == []
    projected = service.to_renderer_items(plan)[0]
    assert projected["imageUrl"].startswith("data:image/svg+xml;base64,")


def test_missing_required_visual_without_fallback_blocks_approval():
    communication = by_artifact()["communication_card"]
    service = V2VisualAssetPlanService()
    plan = service.build(communication)
    missing = plan.visual_items[0].model_copy(update={
        "status": "failed", "asset_id": None, "fallback_asset_id": None,
    })
    plan = plan.model_copy(update={"visual_items": [missing]})

    assert service.approval_blockers(plan)


def test_missing_required_visual_blocks_material_approval_boundary():
    repos, package = n482_runtime()
    communication = next(item for item in package.materials if item.type == "break_card")
    plan = communication.visualAssetPlan
    missing = plan.visual_items[0].model_copy(update={
        "status": "failed", "asset_id": None, "fallback_asset_id": None,
    })
    broken = communication.model_copy(update={
        "visualAssetPlan": plan.model_copy(update={"visual_items": [missing]})
    })
    repos.generated_materials.save(broken)

    with pytest.raises(ConflictError, match="Required instructional visuals"):
        V2MaterialService(repos).approve_generated(broken.id)


def test_failed_provider_visual_uses_fallback_and_single_item_retry_is_isolated():
    repos, package = n482_runtime()
    scenario = next(item for item in package.materials if item.type == "scenario_cards")
    target = scenario.visualAssetPlan.visual_items[0]
    untouched = {
        item.id: (item.status, item.asset_id)
        for item in scenario.visualAssetPlan.visual_items[1:]
    }

    # The configured mock provider cannot supply a semantic production image.
    # The execution path retries within its bound, then exposes the deterministic
    # fallback for only the requested item.
    updated = V2LessonPackageService(repos).prepare_material_visual(
        scenario.id, target.id, force_generation=True
    )
    completed = next(item for item in updated.visualAssetPlan.visual_items if item.id == target.id)
    assert completed.status == "failed"
    assert completed.asset_id == completed.fallback_asset_id
    assert completed.design_constraints["fallbackVisible"] is True
    assert {
        item.id: (item.status, item.asset_id)
        for item in updated.visualAssetPlan.visual_items[1:]
    } == untouched
    renderer = next(item for item in updated.content["visualItems"] if item["id"] == target.id)
    assert renderer["imageUrl"].startswith("data:image/svg+xml;base64,")


def test_duplicate_semantic_visual_and_cross_semantic_asset_reuse_are_detected():
    scenario = by_artifact()["scenario_cards"]
    service = V2VisualAssetPlanService()
    plan = service.build(scenario)
    first = plan.visual_items[0].model_copy(update={"asset_id": "asset-shared"})
    duplicate = deepcopy(first).model_copy(update={"id": "duplicate"})
    plan = plan.model_copy(update={"visual_items": [first, duplicate]})

    codes = {issue.code for issue in service.validate(plan, scenario)}
    assert "duplicate_semantic_visual" in codes
    assert "visual_count_or_semantics_mismatch" in codes


def test_ai_prompts_never_request_embedded_instructional_text():
    first_then = by_artifact()["first_then_board"]
    service = V2VisualAssetPlanService()
    plan = service.build(first_then)
    assert all("text" in (item.negative_prompt or "") for item in plan.visual_items)
    assert not service.validate(plan, first_then)

    invalid = plan.visual_items[0].model_copy(update={
        "prompt": "Create a card and include text reading FIRST.",
    })
    invalid_plan = plan.model_copy(update={
        "visual_items": [invalid, *plan.visual_items[1:]]
    })
    assert "embedded_instructional_text_requested" in {
        issue.code for issue in service.validate(invalid_plan, first_then)
    }


def test_n482_visual_plan_snapshot_is_semantic_and_low_clutter():
    _repos, package = n482_runtime()
    plans = {item.type: item.visualAssetPlan for item in package.materials}

    assert sum(len(plan.visual_items) for plan in plans.values() if plan) == 23
    assert len(plans["blue_line_activity"].visual_items) == 6
    assert len([item for item in plans["blue_line_activity"].visual_items if item.semantic_key.startswith("station:")]) == 3
    assert [item.role for item in plans["first_then_board"].visual_items] == ["first", "then"]
    assert len([item for item in plans["token_board"].visual_items if item.semantic_key.startswith("token-instance:")]) == 5
    assert len(plans["scenario_cards"].visual_items) == 3
    assert len(plans["visual_timer"].visual_items) == 3
    assert len(plans["break_card"].visual_items) == 1
    assert all(
        item.design_constraints["lowClutter"] is True
        and item.design_constraints["literalNeutral"] is True
        for plan in plans.values() if plan for item in plan.visual_items
    )


def test_n482_fallback_artwork_is_distinct_and_contains_no_embedded_text():
    _repos, package = n482_runtime()
    plans = {item.type: item.visualAssetPlan for item in package.materials}
    service = V2VisualAssetPlanService()

    groups = {
        "scenario_cards": plans["scenario_cards"].visual_items,
        "first_then_board": plans["first_then_board"].visual_items,
        "stations": [
            item
            for item in plans["blue_line_activity"].visual_items
            if item.semantic_key.startswith("station:")
        ],
    }
    for items in groups.values():
        payloads = [service.deterministic_svg_data_url(item) for item in items]
        assert len(payloads) == len(set(payloads))
        for payload in payloads:
            svg = base64.b64decode(payload.split(",", 1)[1]).decode("utf-8")
            assert "<text" not in svg.casefold()
            assert "angry" not in svg.casefold()
            assert "#ff0000" not in svg.casefold()


def test_n482_pdf_vector_fallbacks_are_visibly_distinct_by_context():
    _repos, package = n482_runtime()
    planner = V2VisualAssetPlanService()
    plans = {item.type: item.visualAssetPlan for item in package.materials}
    groups = {
        "scenario_cards": plans["scenario_cards"].visual_items,
        "first_then_board": plans["first_then_board"].visual_items,
        "stations": [
            item for item in plans["blue_line_activity"].visual_items
            if item.semantic_key.startswith("station:")
        ],
    }

    for items in groups.values():
        rendered = []
        for item in items:
            projection = planner.to_renderer_items(
                plans[
                    "scenario_cards"
                    if item.role == "scenario"
                    else "first_then_board"
                    if item.role in {"first", "then"}
                    else "blue_line_activity"
                ]
            )
            content = next(value for value in projection if value["id"] == item.id)
            drawing = V2PrintableLessonKitService._deterministic_visual(
                content, width=144, height=108
            )
            svg = renderSVG.drawToString(drawing)
            assert "<text" not in svg.casefold()
            rendered.append(svg)
        assert len(rendered) == len(set(rendered))


def test_complete_image_preparation_includes_blue_line_station_visuals():
    repos, package = n482_runtime()
    service = V2LessonPackageService(repos)

    service.prepare_product_images(package.id)

    activity = next(
        item
        for item in service.get_product(package.id).materials
        if item.type == "blue_line_activity"
    )
    stations = [
        item
        for item in activity.visualAssetPlan.visual_items
        if item.semantic_key.startswith("station:")
    ]
    assert len(stations) == 3
    assert all(item.status == "failed" for item in stations)
    assert all(item.asset_id == item.fallback_asset_id for item in stations)
    assert all(item.design_constraints["fallbackVisible"] for item in stations)
