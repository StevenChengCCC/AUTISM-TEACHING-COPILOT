import pytest

from app.core.exceptions import ValidationError, VersionConflictError
from app.schemas.v2_dto import (
    LessonPackageUpdateRequest,
    LessonDraftMaterialAttachRequest,
    MaterialLibraryCreateRequest,
    QuestionAnswerUpdate,
)
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_repositories import V2Repositories


def planned_chat(repos: V2Repositories):
    service = V2LessonChatService(repos)
    chat = service.submit_request(
        service.start("a102").conversation_id,
        'Independently request “Break, please” using speech or AAC during transitions.',
    )
    return service, chat


def question(chat, field):
    return next(item for item in chat.questions if item.field == field)


def test_unselected_suggestions_do_not_enter_decision_and_defaults_are_distinct():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    materials = question(chat, "selectedMaterials")
    initial = next(item for item in chat.draft.decisions if item.field == "material_requests")
    assert initial.source == "ai_recommended"

    selected = materials.options[0]
    chat = service.update_answer(
        chat.conversation_id,
        materials.id,
        QuestionAnswerUpdate(
            selectedOptionIds=[selected.id], expectedDraftVersion=chat.draft.version
        ),
    )
    decision = next(item for item in chat.draft.decisions if item.field == "material_requests")
    assert decision.source == "teacher_selected"
    assert decision.option_ids == [selected.id]
    assert [item.request_id for item in decision.value.materials] == [selected.id]


def test_teacher_edit_overrides_ai_wording_and_custom_material_survives_resume():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    goal = question(chat, "goalText")
    chat = service.update_answer(
        chat.conversation_id,
        goal.id,
        QuestionAnswerUpdate(
            selectedOptionIds=[goal.options[0].id], expectedDraftVersion=chat.draft.version
        ),
    )
    verbatim = 'Independently say or select “Break, please”.'
    chat = service.update_answer(
        chat.conversation_id,
        goal.id,
        QuestionAnswerUpdate(customAnswer=verbatim, expectedDraftVersion=chat.draft.version),
    )
    decision = next(item for item in chat.draft.decisions if item.field == "goal")
    assert decision.source == "teacher_edited"
    assert decision.value.interpreted_goal == verbatim
    assert chat.draft.goal_text == verbatim

    materials = question(chat, "selectedMaterials")
    custom = "Two-minute visual timer with a blue countdown"
    chat = service.update_answer(
        chat.conversation_id,
        materials.id,
        QuestionAnswerUpdate(customAnswer=custom, expectedDraftVersion=chat.draft.version),
    )
    resumed = service.start("a102", resume_existing=True)
    resumed_materials = question(resumed, "selectedMaterials")
    assert resumed_materials.custom_answer == custom
    assert any(option.value == custom for option in resumed_materials.options)
    unsupported = next(option for option in resumed_materials.options if option.value == custom)
    assert unsupported.supported is False
    assert custom in resumed.draft.selected_materials
    assert resumed.can_generate is False


def test_unsupported_custom_material_is_not_remapped_or_generated():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    materials = question(chat, "selectedMaterials")
    custom = "Scented holographic spinner"
    chat = service.update_answer(
        chat.conversation_id,
        materials.id,
        QuestionAnswerUpdate(customAnswer=custom, expectedDraftVersion=chat.draft.version),
    )
    assert chat.draft.selected_materials == [custom]
    decision = next(item for item in chat.draft.decisions if item.field == "material_requests")
    assert decision.value.materials[0].custom_label == custom
    assert decision.value.materials[0].supported is False
    with pytest.raises(ValidationError, match="Unsupported material requests"):
        V2LessonPackageService(repos).generate_product(
            service.to_dto(chat).draft
        )

    materials = question(chat, "selectedMaterials")
    supported = next(option for option in materials.options if option.supported)
    saved = service.update_answer(
        chat.conversation_id,
        materials.id,
        QuestionAnswerUpdate(
            selectedOptionIds=[supported.id, *materials.selected_option_ids],
            customAnswer=custom,
            saveUnsupportedForFuture=True,
            expectedDraftVersion=chat.draft.version,
        ),
    )
    future = next(
        item for item in next(
            item for item in saved.draft.decisions if item.field == "material_requests"
        ).value.materials if item.custom_label == custom
    )
    assert future.origin == "future_unsupported"
    assert future.required is False


def test_follow_up_messages_are_structured_and_original_is_audited():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    message = "Use a 7-second wait time before the next prompt."
    chat = service.submit_request(chat.conversation_id, message)
    change = chat.draft.structured_changes[-1]
    assert change.change_type == "prompting_change"
    assert change.original_message == message
    assert chat.draft.prompting_start == message
    assert message not in chat.draft.custom_notes


def test_expected_draft_revision_prevents_stale_overwrite():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    goal = question(chat, "goalText")
    stale_version = chat.draft.version
    service.update_answer(
        chat.conversation_id,
        goal.id,
        QuestionAnswerUpdate(
            selectedOptionIds=[goal.options[0].id], expectedDraftVersion=stale_version
        ),
    )
    with pytest.raises(VersionConflictError, match="changed"):
        service.update_answer(
            chat.conversation_id,
            goal.id,
            QuestionAnswerUpdate(customAnswer="stale edit", expectedDraftVersion=stale_version),
        )


def test_explicit_recommendation_refresh_preserves_prior_custom_decisions():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    contexts = question(chat, "scenarios")
    custom = "art activity to cleanup"
    chat = service.update_answer(
        chat.conversation_id,
        contexts.id,
        QuestionAnswerUpdate(customAnswer=custom, expectedDraftVersion=chat.draft.version),
    )
    decision_before = next(item for item in chat.draft.decisions if item.field == "practice_contexts")
    refreshed = service.refresh_recommendations(chat.conversation_id, chat.draft.version)
    refreshed_contexts = question(refreshed, "scenarios")
    decision_after = next(item for item in refreshed.draft.decisions if item.field == "practice_contexts")
    assert refreshed_contexts.custom_answer == custom
    assert refreshed_contexts.selected_option_ids == decision_before.option_ids
    assert decision_after.model_dump() == decision_before.model_dump()


def test_goal_edit_creates_package_revision_and_invalidates_dependent_outputs():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    for field in ("goalText", "scenarios"):
        item = question(chat, field)
        chat = service.update_answer(
            chat.conversation_id,
            item.id,
            QuestionAnswerUpdate(
                selectedOptionIds=[item.options[0].id],
                expectedDraftVersion=chat.draft.version,
            ),
        )
    materials = question(chat, "selectedMaterials")
    chat = service.update_answer(
        chat.conversation_id,
        materials.id,
        QuestionAnswerUpdate(
            selectedOptionIds=[option.id for option in materials.options if option.supported],
            expectedDraftVersion=chat.draft.version,
        ),
    )
    packages = V2LessonPackageService(repos)
    draft = service.to_dto(chat).draft
    draft = draft.model_copy(update={"packageContentPlan": packages.preview_content_plan(draft)})
    package = packages.generate_product(draft)
    new_goal = "Request a break independently in three transitions."
    updated = packages.update_product(
        package.id,
        LessonPackageUpdateRequest(
            documentContent={**package.documentContent, "goal": new_goal},
            expectedVersion=package.version,
        ),
    )
    assert updated.version == package.version + 1
    assert updated.goal == updated.targetSkill == updated.objective == new_goal
    assert {"materials", "data_sheet", "teaching_flow"}.issubset(updated.staleOutputs)
    revised_goal = next(item for item in updated.teacherDecisions if item.field == "goal")
    assert revised_goal.source == "teacher_edited"
    assert revised_goal.value.observable_behavior == new_goal


def test_library_selection_preserves_versioned_configuration():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    goal = question(chat, "goalText")
    chat = service.update_answer(
        chat.conversation_id,
        goal.id,
        QuestionAnswerUpdate(
            customAnswer="Independently request a break during transitions.",
            expectedDraftVersion=chat.draft.version,
        ),
    )
    library = V2MaterialService(repos)
    item = library.create_library_item(
        MaterialLibraryCreateRequest(
            title="Concrete First–Then Board",
            type="first_then_board",
            thumbnailLabel="FIRST → THEN",
            configuration={"slots": 2, "symbolStyle": "literal", "accent": "blue"},
            compatibleGoalTerms=["break"],
            compatibleProfileFactorIds=["first-then", "blue-accent"],
        )
    )
    attached = library.attach_to_lesson_draft(
        chat.draft.id, LessonDraftMaterialAttachRequest(materialId=item.id)
    )
    decision = next(item for item in attached.decisions if item.field == "material_requests")
    reused = next(item for item in decision.value.materials if item.origin == "library_reused")
    assert reused.library_material_id == item.id
    assert reused.library_material_version == item.version
    assert reused.library_configuration == item.configuration


def test_n482_decisions_round_trip_through_persistence_and_api_dto():
    repos = V2Repositories()
    service, chat = planned_chat(repos)
    goal_text = 'Independently request “Break, please” using speech or AAC during transitions.'
    goal = question(chat, "goalText")
    chat = service.update_answer(
        chat.conversation_id, goal.id,
        QuestionAnswerUpdate(customAnswer=goal_text, expectedDraftVersion=chat.draft.version),
    )
    contexts = [
        "transit-map activity to table work",
        "art activity to cleanup",
        "free choice to shared reading",
    ]
    for custom in contexts:
        item = question(chat, "scenarios")
        chat = service.update_answer(
            chat.conversation_id,
            item.id,
            QuestionAnswerUpdate(
                selectedOptionIds=item.selected_option_ids,
                customAnswer=custom,
                expectedDraftVersion=chat.draft.version,
            ),
        )
    materials = [
        "personalized Blue Line activity",
        "Break, Please communication card",
        "concrete First–Then board",
        "five-bus-token board",
        "two-minute visual timer",
        "transition scenario cards",
        "goal-specific data sheet",
        "lesson summary",
    ]
    for index, custom in enumerate(materials):
        item = question(chat, "selectedMaterials")
        chat = service.update_answer(
            chat.conversation_id,
            item.id,
            QuestionAnswerUpdate(
                selectedOptionIds=[] if index == 0 else item.selected_option_ids,
                customAnswer=custom,
                expectedDraftVersion=chat.draft.version,
            ),
        )
    persisted = repos.chats.get(chat.conversation_id)
    payload = service.to_dto(persisted).model_dump(mode="json", by_alias=True)
    restored = type(service.to_dto(persisted)).model_validate(payload)
    assert {item["field"] for item in payload["draft"]["decisions"]} == {
        "goal", "practice_contexts", "material_requests"
    }
    context_decision = next(item for item in restored.draft.decisions if item.field == "practice_contexts")
    material_decision = next(item for item in restored.draft.decisions if item.field == "material_requests")
    assert [item.label for item in context_decision.value.contexts] == contexts
    assert [item.custom_label for item in material_decision.value.materials] == materials
    assert all(item.request_id.startswith("custom-") for item in material_decision.value.materials)
    assert all(item.profile_factor_ids for item in material_decision.value.materials)
