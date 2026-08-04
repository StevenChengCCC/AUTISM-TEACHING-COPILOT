from __future__ import annotations

from copy import deepcopy
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api import v2_routes
from app.core.exceptions import ConflictError
from app.main import app
from app.schemas.v2_dto import (
    LessonPackageDecisionRequest,
    NextSessionRecommendationDto,
    PrintableLessonKitRequest,
    RecommendationEvidence,
    ReviewNextSessionRecommendationRequest,
    SelectiveScenarioRegenerationRequest,
    UpdateNextSessionPlanRequest,
)
from app.services.v2_material_service import V2MaterialService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_next_session_recommendation_service import (
    V2NextSessionRecommendationService,
)
from app.services.v2_next_session_workflow_service import V2NextSessionWorkflowService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_session_outcome_service import V2SessionOutcomeService
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories
from test_v2_goal_progress import _persist_n482_series
from test_v2_next_session_recommendations import _n482_recommendation_case
from test_v2_semantic_revision import n482_runtime
from test_v2_printable_lesson_kit import _settings
from test_v2_sqlalchemy_persistence import _repository
from app.integrations.private_object_storage import LocalPrivateObjectStorage


def _approved_n482_case():
    repos, package = n482_runtime()
    materials = V2MaterialService(repos)
    for item in package.materials:
        materials.review_generated(item.id)
        materials.approve_generated(item.id)
    current = repos.lesson_packages.get(package.id)
    _n482_recommendation_case(repos, current)
    outcome = repos.session_outcomes.list()[0]
    recommendations = V2NextSessionRecommendationService(repos).generate(
        "n482", outcome.goalId, outcome.goalRevision
    )
    review = V2NextSessionRecommendationService(repos)
    selected = []
    for item in recommendations:
        if item.type in {
            "reuse",
            "modify_material",
            "add_generalization",
            "prompt_fading",
        }:
            action = "edited" if item.type == "prompt_fading" else "accepted"
            reviewed = review.review(
                item.id,
                ReviewNextSessionRecommendationRequest(
                    action=action,
                    teacherEditedText=(
                        "Fade one prompt only in stable opportunities; restore support immediately."
                        if action == "edited"
                        else None
                    ),
                    expectedVersion=item.version,
                ),
            )
            selected.append(reviewed)
        elif item.type == "reuse" or item.title == "Keep speech and AAC equally valid":
            selected.append(
                review.review(
                    item.id,
                    ReviewNextSessionRecommendationRequest(
                        action="accepted", expectedVersion=item.version
                    ),
                )
            )
    # Preserve-response-mode recommendations are type=reuse but may not have
    # material IDs; make sure the generated fixture includes it as accepted.
    for item in recommendations:
        if item.title == "Keep speech and AAC equally valid" and not any(
            current.id == item.id for current in selected
        ):
            selected.append(
                review.review(
                    item.id,
                    ReviewNextSessionRecommendationRequest(
                        action="accepted", expectedVersion=item.version
                    ),
                )
            )
    return repos, repos.lesson_packages.get(package.id), recommendations, selected


def test_n482_impact_plan_reuses_stable_supports_and_revises_only_dependencies():
    repos, package, recommendations, selected = _approved_n482_case()
    before = deepcopy(package)
    plan = V2NextSessionWorkflowService(repos).create_plan(package.id, package.version)

    reusable = {item.materialType for item in plan.reusableMaterials}
    revised = {item.materialType for item in plan.materialsToRevise}
    assert {"break_card", "visual_timer", "token_board"} <= reusable
    assert {
        "scenario_cards",
        "teacher_cue_card",
        "data_sheet",
        "summary_template",
    } <= revised
    assert reusable.isdisjoint(revised)
    assert plan.proposedLessonSpecRevision.acceptedRecommendationIds == sorted(
        item.id for item in selected
    )
    assert all(item.status in {"accepted", "edited"} for item in selected)
    excluded = {
        item.id
        for item in repos.next_session_recommendations.list()
        if item.status in {"pending", "rejected"}
    }
    assert excluded.isdisjoint(
        plan.proposedLessonSpecRevision.acceptedRecommendationIds
    )
    assert plan.proposedLessonSpecRevision.teacherEditedRecommendationContent
    assert plan.proposedLessonSpecRevision.goalSeriesBoundary == "continue"
    proposed = plan.proposedLessonSpecRevision.lessonSpec
    assert proposed.communication_plan == package.lessonSpec.communication_plan
    assert proposed.reinforcement_plan == package.lessonSpec.reinforcement_plan
    assert proposed.access_plan == package.lessonSpec.access_plan
    assert proposed.prompting_plan.wait_time_seconds == 5
    assert (
        proposed.prompting_plan.prohibited_prompts
        == package.lessonSpec.prompting_plan.prohibited_prompts
    )
    assert repos.lesson_packages.get(package.id) == before


def test_pending_and_rejected_recommendations_cannot_change_proposed_spec():
    repos, package, recommendations, selected = _approved_n482_case()
    source = recommendations[0]
    repos.next_session_recommendations.save(
        source.model_copy(
            update={
                "id": "pending-duration-change",
                "type": "adjust_duration",
                "status": "pending",
                "recommendation": "The teacher may consider changing duration to 90 minutes.",
                "affectedLessonSpecPaths": ["/duration"],
                "ruleId": "pending-must-not-apply",
                "evidenceFingerprint": "pending-must-not-apply",
                "version": 1,
            }
        )
    )
    repos.next_session_recommendations.save(
        source.model_copy(
            update={
                "id": "rejected-duration-change",
                "type": "adjust_duration",
                "status": "rejected",
                "recommendation": "The teacher may consider changing duration to 1 minute.",
                "affectedLessonSpecPaths": ["/duration"],
                "ruleId": "rejected-must-not-apply",
                "evidenceFingerprint": "rejected-must-not-apply",
                "version": 1,
            }
        )
    )

    plan = V2NextSessionWorkflowService(repos).create_plan(package.id, package.version)
    assert set(plan.proposedLessonSpecRevision.acceptedRecommendationIds) == {
        item.id for item in selected
    }
    assert "pending-duration-change" not in plan.model_dump_json()
    assert "rejected-duration-change" not in plan.model_dump_json()
    assert (
        plan.proposedLessonSpecRevision.lessonSpec.duration
        == package.lessonSpec.duration
    )


def test_create_next_package_preserves_reusable_revisions_and_invalidates_only_revised():
    repos, package, _recommendations, _selected = _approved_n482_case()
    workflow = V2NextSessionWorkflowService(repos)
    plan = workflow.create_plan(package.id, package.version)
    original_by_id = {item.id: item for item in package.materials}
    original_snapshot = deepcopy(package)

    created = workflow.create_package(plan.id, plan.version)
    assert created.id != package.id
    assert repos.lesson_packages.get(package.id) == original_snapshot
    assert created.documentContent["previousPackageId"] == package.id
    by_source = {
        item.materialSpec.source_material_id: item
        for item in created.materials
        if item.materialSpec is not None
    }
    for impact in plan.reusableMaterials:
        clone = by_source[impact.materialId]
        source = original_by_id[impact.materialId]
        assert clone.materialSpec.revision == source.materialSpec.revision
        assert clone.materialSpec.approval == source.materialSpec.approval
        assert clone.visualAssetPlan.visual_items == source.visualAssetPlan.visual_items
    for impact in plan.materialsToRevise:
        clone = by_source[impact.materialId]
        source = original_by_id[impact.materialId]
        assert clone.materialSpec.revision == source.materialSpec.revision + 1
        assert clone.materialSpec.approval.status == "not_reviewed"
        assert clone.status != "approved"

    # Idempotent repeated confirmation returns the same next package.
    persisted_plan = workflow.get_plan(plan.id)
    assert workflow.create_package(plan.id, persisted_plan.version).id == created.id


def test_teacher_override_cannot_keep_semantically_incompatible_material():
    repos, package, _recommendations, _selected = _approved_n482_case()
    workflow = V2NextSessionWorkflowService(repos)
    plan = workflow.create_plan(package.id, package.version)
    scenario = next(
        item for item in plan.materialsToRevise if item.materialType == "scenario_cards"
    )
    assert scenario.safeToKeepExisting
    kept = workflow.update_plan(
        plan.id,
        UpdateNextSessionPlanRequest(
            action="keep_existing",
            materialId=scenario.materialId,
            reason="Teacher confirmed the existing examples still fit.",
            expectedVersion=plan.version,
        ),
    )
    assert scenario.materialId in {item.materialId for item in kept.reusableMaterials}

    # A failed semantic check remains non-overridable even if a client tampers
    # with the impact-plan payload before the next optimistic-lock write.
    reusable_source = kept.reusableMaterials[0]
    incompatible = scenario.model_copy(
        update={
            "safeToKeepExisting": False,
            "compatibilityChecks": [
                reusable_source.compatibilityChecks[0].model_copy(
                    update={"passed": False}
                )
            ],
        }
    )
    forced = repos.next_session_impact_plans.save(
        kept.model_copy(
            update={
                "reusableMaterials": [
                    item
                    for item in kept.reusableMaterials
                    if item.materialId != scenario.materialId
                ],
                "materialsToRevise": [incompatible, *kept.materialsToRevise],
            }
        )
    )
    with pytest.raises(ConflictError):
        workflow.update_plan(
            forced.id,
            UpdateNextSessionPlanRequest(
                action="keep_existing",
                materialId=scenario.materialId,
                reason="Unsafe test override",
                expectedVersion=forced.version,
            ),
        )


def test_selective_scenario_regeneration_preserves_other_visual_assets():
    repos, package, _recommendations, _selected = _approved_n482_case()
    workflow = V2NextSessionWorkflowService(repos)
    plan = workflow.create_plan(package.id, package.version)
    created = workflow.create_package(plan.id, plan.version)
    material = next(item for item in created.materials if item.type == "scenario_cards")
    scenario_id = material.materialSpec.content.scenarios[0].id
    before_assets = {
        item.semantic_key: item.asset_id
        for item in material.visualAssetPlan.visual_items
    }

    revised = workflow.regenerate_scenario(
        created.id,
        material.id,
        SelectiveScenarioRegenerationRequest(
            scenarioId=scenario_id,
            teacherInstruction="Offer Break, please by speech or AAC, wait five seconds, then honor it.",
            expectedMaterialVersion=material.version,
        ),
    )
    assert revised.materialSpec.revision == material.materialSpec.revision + 1
    assert revised.materialSpec.approval.status == "not_reviewed"
    for item in revised.visualAssetPlan.visual_items:
        if scenario_id not in item.semantic_key:
            assert item.asset_id == before_assets[item.semantic_key]

    # Saving one changed artifact re-evaluates the whole package. Reused
    # visual plans must remain linked to their cloned MaterialSpec identities.
    revalidated_package = repos.lesson_packages.get(created.id)
    reusable_source_ids = {item.materialId for item in plan.reusableMaterials}
    for item in revalidated_package.materials:
        if item.materialSpec and item.materialSpec.source_material_id in reusable_source_ids:
            assert item.visualAssetPlan.material_id == item.materialSpec.id
            assert item.materialSpec.semantic_validation.status == "passed"
            assert item.materialSpec.safety_validation.status == "passed"
            assert item.materialSpec.approval.status == "approved"
            assert item.status == "approved"
    assert revalidated_package.safetyReview.status != "blocked"


def test_next_session_pdf_contains_teacher_edit_and_current_material_revisions(tmp_path):
    repos, package, _recommendations, _selected = _approved_n482_case()
    workflow = V2NextSessionWorkflowService(repos)
    plan = workflow.create_plan(package.id, package.version)
    created = workflow.create_package(plan.id, plan.version)
    teacher_edit = "Fade one prompt only in stable opportunities; restore support immediately."
    cue = next(item for item in created.materials if item.type == "teacher_cue_card")
    assert any(
        teacher_edit in prompt for prompt in cue.materialSpec.content.prompts_used
    )

    materials = V2MaterialService(repos)
    for item in repos.lesson_packages.get(created.id).materials:
        if item.status != "approved":
            reviewed = materials.review_generated(item.id)
            materials.approve_generated(reviewed.id)
    current = repos.lesson_packages.get(created.id)
    approved = V2LessonPackageService(repos).approve_product(
        current.id,
        LessonPackageDecisionRequest(
            expectedVersion=current.version,
            reason="Next-session teacher-edit PDF regression",
        ),
    )
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)
    artifact = service.create_artifact(
        approved.id,
        PrintableLessonKitRequest(
            materialIds=[item.id for item in approved.materials],
            pageSize="Letter",
            reviewedConfirmation=True,
        ),
    )
    job = repos.export_jobs.get(artifact.artifactId)
    body = storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
    text = " ".join(
        "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(body)).pages).split()
    )
    assert teacher_edit.casefold() in text.casefold()
    assert artifact.materialRevisions == {
        item.id: item.materialSpec.revision for item in approved.materials
    }


def test_goal_definition_change_creates_boundary_without_mutating_prior_series():
    repos, package = n482_runtime()
    outcomes = _persist_n482_series(repos, package)
    prior_series = [item.model_copy(deep=True) for item in outcomes]
    goal_id = V2SessionOutcomeService.goal_id(package.lessonSpec)
    recommendation = NextSessionRecommendationDto(
        id="teacher-goal-change",
        learnerId="n482",
        goalId=goal_id,
        goalRevision=package.lessonSpec.revision,
        type="teacher_question",
        title="Teacher-authored observable behavior revision",
        recommendation="Learner independently requests a break and returns to the marked step.",
        evidence=[
            RecommendationEvidence(
                sessionId=outcomes[-1].sessionId,
                description="Teacher explicitly requested a new observable response boundary.",
                metricPath="teacherDecision.observableBehavior",
                observedValue=True,
            )
        ],
        confidence="high",
        confidenceReason="Explicit teacher decision.",
        affectedLessonSpecPaths=["/goal/observableBehavior"],
        status="edited",
        teacherEditedText="Learner independently requests a break and returns to the marked step.",
        ruleId="teacher-goal-boundary-v1",
        evidenceFingerprint="teacher-goal-boundary",
    )
    repos.next_session_recommendations.save(recommendation)
    plan = V2NextSessionWorkflowService(repos).create_plan(package.id, package.version)
    assert plan.proposedLessonSpecRevision.goalSeriesBoundary == "new"
    assert plan.proposedLessonSpecRevision.proposedGoalId != goal_id
    assert repos.session_outcomes.list() == prior_series


def test_impact_plan_persists_across_repository_restart(tmp_path):
    memory, package, recommendations, _selected = _approved_n482_case()
    _engine, factory, repository = _repository(
        f"sqlite:///{tmp_path / 'next-session-workflow.db'}"
    )
    repository.learners.save(memory.learners.get("n482"))
    persisted_package = repository.lesson_packages.save(package)
    for material in package.materials:
        repository.generated_materials.save(material)
    for recommendation in memory.next_session_recommendations.list():
        repository.next_session_recommendations.save(recommendation)
    plan = V2NextSessionWorkflowService(repository).create_plan(
        persisted_package.id, persisted_package.version
    )

    restarted = SQLAlchemyV2Repositories(
        factory,
        repository.config,
        organization_external_id="org-one",
        user_external_id="teacher-one",
        seed_synthetic=False,
    )
    loaded = V2NextSessionWorkflowService(restarted).get_plan(plan.id)
    assert loaded == plan
    assert loaded.proposedLessonSpecRevision.acceptedRecommendationIds
    created = V2NextSessionWorkflowService(restarted).create_package(
        loaded.id, loaded.version
    )
    restarted_again = SQLAlchemyV2Repositories(
        factory,
        repository.config,
        organization_external_id="org-one",
        user_external_id="teacher-one",
        seed_synthetic=False,
    )
    persisted_created = restarted_again.lesson_packages.get(created.id)
    persisted_plan = V2NextSessionWorkflowService(restarted_again).get_plan(plan.id)
    assert persisted_created is not None
    assert {item.id for item in persisted_created.materials} == {
        item.id for item in created.materials
    }
    assert persisted_plan.createdPackageId == created.id
    assert persisted_plan.status == "package_created"


def test_next_session_workflow_api_contract(monkeypatch):
    repos, package, _recommendations, _selected = _approved_n482_case()
    workflow = V2NextSessionWorkflowService(repos)
    monkeypatch.setattr(v2_routes, "V2NextSessionWorkflowService", lambda: workflow)
    client = TestClient(app)

    planned = client.post(
        f"/api/v2/lesson-packages/{package.id}/next-session-plan",
        json={"expectedPackageRevision": package.version},
    )
    assert planned.status_code == 200
    payload = planned.json()
    assert payload["reusableMaterials"] and payload["materialsToRevise"]
    fetched = client.get(f"/api/v2/next-session-plans/{payload['id']}")
    assert (
        fetched.status_code == 200 and fetched.json()["version"] == payload["version"]
    )
    created = client.post(
        f"/api/v2/next-session-plans/{payload['id']}/create-package",
        json={"expectedPlanVersion": payload["version"]},
    )
    assert created.status_code == 200
    assert created.json()["documentContent"]["previousPackageId"] == package.id
