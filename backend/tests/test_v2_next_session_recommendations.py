from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api import v2_routes
from app.core.exceptions import ValidationError
from app.main import app
from app.schemas.v2_dto import (
    NextSessionRecommendationDto,
    RecommendationEvidence,
    ReviewNextSessionRecommendationRequest,
)
from app.services.v2_next_session_recommendation_service import (
    V2NextSessionRecommendationService,
)
from app.services.v2_repositories import V2Repositories
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories
from test_v2_goal_progress import _persist_n482_series, n482_package_for_progress
from test_v2_sqlalchemy_persistence import _repository


def _n482_recommendation_case(repos, package):
    outcomes = _persist_n482_series(repos, package)
    by_type = {item.type: item.id for item in package.materials}
    break_card = by_type["break_card"]
    timer = by_type["visual_timer"]
    scenario = by_type["scenario_cards"]
    for index, outcome in enumerate(outcomes):
        revised_trials = [
            trial.model_copy(update={
                "materialIdsUsed": list(dict.fromkeys([
                    *trial.materialIdsUsed, break_card, timer,
                ])),
            })
            for trial in outcome.trials
        ]
        revised_materials = outcome.materials.model_copy(update={
            "usedMaterialIds": list(dict.fromkeys([
                *outcome.materials.usedMaterialIds, break_card, timer,
            ])),
            "unusedMaterialIds": [
                item for item in outcome.materials.unusedMaterialIds
                if item not in {break_card, timer}
            ],
            "unhelpfulMaterialIds": [scenario] if index == len(outcomes) - 1 else [],
        })
        repos.session_outcomes.save(outcome.model_copy(update={
            "trials": revised_trials,
            "materials": revised_materials,
        }))
    return by_type


def test_n482_recommendations_are_evidence_linked_and_review_only(
    n482_package_for_progress,
):
    repos = V2Repositories()
    material_ids = _n482_recommendation_case(repos, n482_package_for_progress)
    learner_before = deepcopy(repos.learners.get("n482"))
    package_before = deepcopy(repos.lesson_packages.get(n482_package_for_progress.id))
    service = V2NextSessionRecommendationService(repos)
    first_outcome = repos.session_outcomes.list()[0]
    recommendations = service.generate(
        "n482",
        first_outcome.goalId,
        first_outcome.goalRevision,
    )

    assert recommendations
    assert all(item.status == "pending" and item.teacherReviewRequired for item in recommendations)
    assert all(item.evidence for item in recommendations)
    assert all(
        evidence.sessionId and evidence.metricPath and evidence.observedValue is not None
        for item in recommendations for evidence in item.evidence
    )
    assert repos.learners.get("n482") == learner_before
    assert repos.lesson_packages.get(n482_package_for_progress.id) == package_before

    reuse = next(item for item in recommendations if "communication and timing" in item.title)
    assert {material_ids["break_card"], material_ids["visual_timer"]} <= set(reuse.affectedMaterialIds)
    assert set(reuse.affectedMaterialTypes) == {"break_card", "visual_timer"}
    assert "causality" in reuse.confidenceReason

    modification = next(item for item in recommendations if item.type == "modify_material")
    assert modification.affectedMaterialIds == [material_ids["scenario_cards"]]
    assert modification.affectedMaterialTypes == ["scenario_cards"]
    assert modification.evidence[0].metricPath == "materials.unhelpfulMaterialIds"
    assert "does not establish material causality" in modification.evidence[0].description
    assert "teacher" in modification.evidence[0].description.casefold()

    context = next(item for item in recommendations if item.type == "add_generalization")
    assert "free choice to shared reading" in context.title
    assert context.affectedLessonSpecPaths == ["/contexts"]
    assert all(item.contextLabel == "free choice to shared reading" for item in context.evidence)

    access = next(item for item in recommendations if item.title == "Keep speech and AAC equally valid")
    assert access.affectedLessonSpecPaths == ["/communicationPlan/acceptedModes"]
    assert all("speech=" in str(item.observedValue) and "AAC=" in str(item.observedValue) for item in access.evidence)

    fading = next(item for item in recommendations if item.type == "prompt_fading")
    assert len(fading.evidence) == 3
    assert "only in opportunities" in fading.recommendation


def test_insufficient_data_preserves_plan_instead_of_forcing_change(
    n482_package_for_progress,
):
    repos = V2Repositories()
    outcomes = _persist_n482_series(repos, n482_package_for_progress, counts=(1,))
    recommendations = V2NextSessionRecommendationService(repos).generate(
        "n482", outcomes[0].goalId, outcomes[0].goalRevision
    )
    assert [item.type for item in recommendations] == ["collect_more_data"]
    assert "before changing" in recommendations[0].recommendation
    assert recommendations[0].evidence[0].sessionId == outcomes[0].sessionId


def test_rejection_is_persisted_and_generation_does_not_reactivate_it(
    n482_package_for_progress,
):
    repos = V2Repositories()
    _n482_recommendation_case(repos, n482_package_for_progress)
    outcome = repos.session_outcomes.list()[0]
    service = V2NextSessionRecommendationService(repos)
    recommendation = service.generate("n482", outcome.goalId, outcome.goalRevision)[0]
    rejected = service.review(
        recommendation.id,
        ReviewNextSessionRecommendationRequest(
            action="rejected", expectedVersion=recommendation.version
        ),
    )
    assert rejected.status == "rejected"
    regenerated = service.generate("n482", outcome.goalId, outcome.goalRevision)
    assert next(item for item in regenerated if item.id == rejected.id).status == "rejected"


def test_teacher_edit_is_preserved_verbatim_with_provenance(
    n482_package_for_progress,
):
    repos = V2Repositories()
    outcome = _persist_n482_series(repos, n482_package_for_progress, counts=(1,))[0]
    service = V2NextSessionRecommendationService(repos)
    recommendation = service.generate("n482", outcome.goalId, outcome.goalRevision)[0]
    exact = "  Keep the current contexts; collect two more sessions.\nTeacher wording stays exact.  "
    edited = service.review(
        recommendation.id,
        ReviewNextSessionRecommendationRequest(
            action="edited",
            teacherEditedText=exact,
            expectedVersion=recommendation.version,
        ),
    )
    assert edited.teacherEditedText == exact
    assert edited.reviewHistory[-1].teacherText == exact
    assert edited.reviewHistory[-1].actorType == "teacher"
    assert edited.reviewedAt is not None


def test_generated_language_respects_clinical_and_communication_boundaries(
    n482_package_for_progress,
):
    repos = V2Repositories()
    _n482_recommendation_case(repos, n482_package_for_progress)
    outcome = repos.session_outcomes.list()[0]
    recommendations = V2NextSessionRecommendationService(repos).generate(
        "n482", outcome.goalId, outcome.goalRevision
    )
    protected = (
        "diagnose", "prescribe", "treatment is effective", "has mastered",
        "is regressing", "defiant", "remove breaks", "withhold a break",
    )
    text = " ".join(
        f"{item.title} {item.recommendation}" for item in recommendations
    ).casefold()
    assert not any(phrase in text for phrase in protected)
    assert all(
        item.recommendation.startswith("The teacher may consider")
        or item.recommendation.startswith("More observations may be useful")
        for item in recommendations
    )

    unsafe = NextSessionRecommendationDto(
        id="unsafe", learnerId="n482", goalId=outcome.goalId, goalRevision=1,
        type="increase_support", title="Prescribe treatment intensity",
        recommendation="The teacher may consider restrictive procedures.",
        evidence=[RecommendationEvidence(
            sessionId=outcome.sessionId, description="Unsafe test", metricPath="test",
            observedValue=1,
        )],
        confidence="low", confidenceReason="Test", ruleId="unsafe",
        evidenceFingerprint="unsafe",
    )
    with pytest.raises(ValidationError):
        V2NextSessionRecommendationService._validate_safety(unsafe)


def test_recommendations_persist_across_repository_reload(
    tmp_path, n482_package_for_progress,
):
    engine, factory, repository = _repository(
        f"sqlite:///{tmp_path / 'recommendations.db'}"
    )
    _n482_recommendation_case(repository, n482_package_for_progress)
    outcome = repository.session_outcomes.list()[0]
    generated = V2NextSessionRecommendationService(repository).generate(
        "n482", outcome.goalId, outcome.goalRevision
    )
    restarted = SQLAlchemyV2Repositories(
        factory,
        repository.config,
        organization_external_id="org-one",
        user_external_id="teacher-one",
        seed_synthetic=False,
    )
    loaded = V2NextSessionRecommendationService(restarted).list(
        "n482", goal_id=outcome.goalId, goal_revision=outcome.goalRevision
    )
    assert {item.id for item in loaded} == {item.id for item in generated}
    assert all(item.evidence for item in loaded)
    engine.dispose()


def test_recommendation_api_generate_list_and_review(
    monkeypatch, n482_package_for_progress,
):
    repos = V2Repositories()
    _n482_recommendation_case(repos, n482_package_for_progress)
    outcome = repos.session_outcomes.list()[0]
    service = V2NextSessionRecommendationService(repos)
    monkeypatch.setattr(
        v2_routes, "V2NextSessionRecommendationService", lambda: service
    )
    client = TestClient(app)
    generated = client.post(
        "/api/v2/learners/n482/next-session-recommendations/generate",
        json={"goalId": outcome.goalId, "goalRevision": outcome.goalRevision},
    )
    assert generated.status_code == 200
    first = generated.json()[0]
    listed = client.get(
        "/api/v2/learners/n482/next-session-recommendations",
        params={"goalId": outcome.goalId, "goalRevision": outcome.goalRevision},
    )
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {
        item["id"] for item in generated.json()
    }
    reviewed = client.patch(
        f"/api/v2/next-session-recommendations/{first['id']}",
        json={"action": "accepted", "expectedVersion": first["version"]},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "accepted"
    assert reviewed.json()["teacherReviewRequired"] is True
