from io import BytesIO

from pypdf import PdfReader

from app.schemas.v2_dto import MaterialUpdateRequest
from app.services.v2_material_service import V2MaterialService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from test_v2_semantic_revision import n482_runtime
from test_v2_print_package_composition import _approve_n482


def test_n482_material_specs_golden_vertical_slice():
    _repos, package = n482_runtime()
    materials = {item.type: item for item in package.materials}

    activity = materials["blue_line_activity"].materialSpec.content
    communication = materials["break_card"].materialSpec.content
    first_then = materials["first_then_board"].materialSpec.content
    token = materials["token_board"].materialSpec.content
    timer = materials["visual_timer"].materialSpec.content
    scenarios = materials["scenario_cards"].materialSpec.content.scenarios
    data = materials["data_sheet"].materialSpec.content
    summary = materials["summary_template"].materialSpec.content

    assert activity.task_name == "Complete the Blue Line"
    assert activity.answer_key_or_expected_sequence == [
        "transit-map activity to table work",
        "art activity to cleanup",
        "free choice to shared reading",
    ]
    assert "Place, point to, or order the 3 station cards" in activity.learner_action
    assert ".." not in activity.learner_action
    assert {"Do not require handwriting", "Avoid fine-motor cutting"} <= set(activity.motor_access_requirements)
    assert communication.exact_communication_phrase == "Break, please"
    assert communication.accepted_communication_modes == ["speech", "AAC"]
    assert communication.teacher_response_after_use == "Honor the request when feasible and begin the 2-minute visual timer."
    assert {"angry or exaggerated faces", "decorative learner photographs"} <= set(communication.prohibited_imagery)
    assert first_then.first_task == "Complete 3 table-work items"
    assert first_then.then_outcome == "2-minute transit-map break"
    assert first_then.completion_criterion == "Complete all 3 table-work items"
    assert token.exact_token_count == 5 and token.token_symbol_or_theme == "bus"
    assert token.earned_reward == "2 minutes with the transit-route map"
    assert token.specific_praise == "You asked for a break by yourself."
    assert not any(term in token.model_dump_json().casefold() for term in ("ipad", "video", "dinosaur", "star"))
    assert timer.duration_minutes == 2 and timer.audio_allowed is False
    assert timer.return_to_task_cue == "Break finished — check First–Then"
    assert len(scenarios) == 3
    assert all(item.wait_time_seconds == 5 for item in scenarios)
    assert all(item.accepted_modalities == ["speech", "AAC"] for item in scenarios)
    assert all(len(item.prompt_sequence) == 4 for item in scenarios)
    assert data.exact_columns == [
        "opportunity", "context", "response_outcome", "independence",
        "prompt_level", "latency_seconds", "response_mode", "break_requested",
        "break_honored", "break_duration_minutes", "returned_to_activity", "notes",
    ]
    assert len(data.prompt_level_definitions) == 4
    assert summary.reporting_fields == [
        "Opportunities completed",
        "Successful responses (independent / prompted)",
        "Responses by mode (Speech / AAC)",
        "Prompt level and latency notes",
        "Break or stop honored / return status",
        "Context comparison",
        "Suggested next generalization step", "Teacher notes",
    ]


def test_renderers_use_typed_content_visual_plan_and_current_revision():
    _repos, package = n482_runtime()
    activity = next(item for item in package.materials if item.type == "blue_line_activity")
    corrupted = activity.model_copy(update={
        "content": {**activity.content, "taskName": "Generic themed worksheet"}
    })

    rendered = V2PrintableLessonKitService._material_content(corrupted)

    assert rendered["taskName"] == "Complete the Blue Line"
    assert corrupted.visualAssetPlan.material_revision == corrupted.materialSpec.revision
    assert len([item for item in corrupted.visualAssetPlan.visual_items if item.semantic_key.startswith("station:")]) == 3


def test_n482_deterministic_pdf_contains_executable_material_content():
    repos, package = _approve_n482()
    body = V2PrintableLessonKitService(repos)._build_pdf(
        package, package.materials, "Letter"
    )
    reader = PdfReader(BytesIO(body))
    text = " ".join(
        "\n".join(page.extract_text() or "" for page in reader.pages).split()
    )

    for expected in (
        "Complete the Blue Line", "Teacher setup", "Station sequence / answer key",
        "Break, please", "Complete 3 table-work items", "2-minute transit-map break",
        "You asked for a break by yourself.", "No alarm or audio cue",
        "Scenario Cards 1", "Teacher wording", "Prompt and independence definitions",
        "Context Comparison", "Teacher Notes", "Accepted responses",
        "Wait 5 seconds before prompting", "Break and return",
        "Teacher judgment overrides this guide",
    ):
        assert expected.casefold() in text.casefold()


def test_visual_accessibility_and_print_layout_contracts():
    _repos, package = n482_runtime()
    by_type = {item.type: item for item in package.materials}
    for material in package.materials:
        if material.visualAssetPlan is None:
            continue
        assert material.visualAssetPlan.material_revision == material.materialSpec.revision
        assert all(item.alt_text.strip() and item.visible_label.strip() for item in material.visualAssetPlan.visual_items)
        assert all(
            item.generation_method != "ai_generated"
            or (item.negative_prompt and "text" in item.negative_prompt.casefold())
            for item in material.visualAssetPlan.visual_items
        )
    for material_type in (
        "blue_line_activity", "first_then_board", "token_board", "scenario_cards", "data_sheet",
    ):
        assert by_type[material_type].printLayout["orientation"] == "landscape"
        assert by_type[material_type].materialSpec.design_constraints.orientation == "landscape"


def test_semantic_edit_rebuilds_visual_plan_and_reruns_validation():
    repos, package = n482_runtime()
    token = next(item for item in package.materials if item.type == "token_board")
    content = token.materialSpec.content.model_dump(mode="json", by_alias=True)
    content["exactTokenCount"] = 4

    revised = V2MaterialService(repos).update_generated(
        token.id,
        MaterialUpdateRequest(
            title=token.title,
            content={**token.content, **content},
            printLayout=token.printLayout,
            expectedVersion=token.version,
        ),
    )

    assert revised.materialSpec.revision == token.materialSpec.revision + 1
    assert revised.visualAssetPlan.material_revision == revised.materialSpec.revision
    assert len([
        item for item in revised.visualAssetPlan.visual_items
        if item.semantic_key.startswith("token-instance:")
    ]) == 4
    assert revised.status == "validation_failed"
    assert "wrong_token_count" in {
        issue.code for issue in revised.materialSpec.semantic_validation.issues
    }
