from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as SchemaValidationError

from app.api import v2_routes
from app.core.exceptions import ConflictError, ValidationError
from app.main import app
from app.schemas.v2_dto import CompleteSessionRequest, SessionCreate, SessionTrialObservation, SessionUseSnapshot, utc_now
from app.services.v2_instructional_constraint_service import build_instructional_constraint_snapshot
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories
from app.services.v2_session_outcome_service import V2SessionOutcomeService
from app.services.v2_session_service import V2SessionService
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories
from test_v2_lesson_spec import n482_draft, n482_learner
from test_v2_sqlalchemy_persistence import _repository


FIXTURE = Path(__file__).parent / "fixtures" / "n482_completed_session.json"


@pytest.fixture(scope="module")
def n482_package():
    repos = V2Repositories()
    learner = n482_learner()
    repos.learners.save(learner)
    snapshot = build_instructional_constraint_snapshot(learner, [])
    draft = n482_draft(snapshot)
    service = V2LessonPackageService(repos)
    plan = service.preview_content_plan(draft)
    return service.generate_product(draft.model_copy(update={"packageContentPlan": plan}))


def _case(package, repos=None):
    repos = repos or V2Repositories()
    if repos.learners.get("n482") is None:
        repos.learners.save(n482_learner())
    if repos.lesson_packages.get(package.id) is None:
        repos.lesson_packages.save(package.model_copy(deep=True))
    session = V2SessionService(repos).create(SessionCreate(
        learnerId="n482",
        goal=package.goal,
        status="planned",
        lessonPackageId=package.id,
    ))
    spec = package.lessonSpec
    snapshot = SessionUseSnapshot(
        id=f"use-{session.id}", sessionId=session.id, learnerId="n482",
        goalId=V2SessionOutcomeService.goal_id(spec), goalRevision=spec.revision,
        goalComparisonKey=V2SessionOutcomeService.goal_comparison_key(spec),
        operationalizedGoal=spec.goal.observable_behavior,
        lessonSpecId=spec.id, lessonSpecRevision=spec.revision,
        packageId=package.id, packageRevision=package.version,
        materialRevisions={item.id: item.materialSpec.revision if item.materialSpec else item.version for item in package.materials},
        materialLabels={item.id: item.title for item in package.materials},
        teacherConfirmedContexts=spec.contexts,
        acceptedResponseModes=spec.communication_plan.accepted_modes,
        promptLevelDefinitions=spec.data_plan.prompt_levels,
        independenceDefinition=spec.data_plan.independence_definition,
        dataMeasures=spec.data_plan.measures,
        plannedOpportunities=spec.goal.success_criterion.total_opportunities,
        startedAt=utc_now(), startedByTeacher="test-teacher", idempotencyKey=f"start-{session.id}",
    )
    session = repos.sessions.save(session.model_copy(update={"status": "in_progress", "use_snapshot": snapshot, "started_at": snapshot.startedAt}))
    service = V2SessionOutcomeService(repos)
    template = service.completion_template(session.id)
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    material_ids = {item.type: item.id for item in package.materials}
    trials = []
    for raw in source["trials"]:
        trial = {key: value for key, value in raw.items() if key != "materialTypesUsed"}
        trial["materialIdsUsed"] = [material_ids[item] for item in raw["materialTypesUsed"]]
        trials.append(trial)
    request = CompleteSessionRequest(
        expectedLessonPackageId=package.id,
        expectedLessonSpecId=package.lessonSpec.id,
        expectedGoalId=V2SessionOutcomeService.goal_id(package.lessonSpec),
        startedAt=source["startedAt"],
        completedAt=source["completedAt"],
        trials=trials,
        generalization=source["generalization"],
        helpfulMaterialIds=[material_ids[item] for item in source["helpfulMaterialTypes"]],
        unhelpfulMaterialIds=[],
        observations=source["observations"],
    )
    return repos, service, session, template, request, material_ids


def test_n482_trial_aggregation_and_response_mode_counting(n482_package):
    _, service, session, template, request, _ = _case(n482_package)
    outcome = service.complete(session.id, request)
    assert template.plannedOpportunities == 5
    assert outcome.opportunities.model_dump() == {"planned": 5, "valid": 5, "cancelled": 0}
    assert outcome.responses.independentSuccessful == 1
    assert outcome.responses.promptedSuccessful == 3
    assert outcome.responses.noResponse == 1
    assert outcome.responses.speechSuccessful == 2
    assert outcome.responses.aacSuccessful == 2


def test_invalid_opportunity_is_excluded_from_totals(n482_package):
    _, service, session, _, request, _ = _case(n482_package)
    cancelled = request.trials[-1].model_copy(update={
        "valid": False, "outcome": "cancelled", "latencySeconds": None,
    })
    outcome = service.complete(
        session.id,
        request.model_copy(update={"trials": [*request.trials[:-1], cancelled]}),
    )
    assert outcome.opportunities.valid == 4
    assert outcome.opportunities.cancelled == 1
    assert outcome.responses.noResponse == 0
    assert outcome.latency.recordedTrialCount == 4


def test_prompt_level_aggregation(n482_package):
    _, service, session, _, request, _ = _case(n482_package)
    outcome = service.complete(session.id, request)
    assert outcome.prompting.promptLevelCounts == {
        "independent": 2, "visual": 1, "model": 1, "brief_verbal": 1,
    }
    assert outcome.prompting.averagePromptLevel == 1.8
    assert outcome.prompting.lowestPromptLevel == "independent"
    assert outcome.prompting.highestPromptLevel == "brief_verbal"


def test_latency_mean_and_median(n482_package):
    _, service, session, _, request, _ = _case(n482_package)
    outcome = service.complete(session.id, request)
    assert outcome.latency.recordedTrialCount == 5
    assert outcome.latency.averageSeconds == 5
    assert outcome.latency.medianSeconds == 5


def test_break_return_context_and_material_aggregation(n482_package):
    _, service, session, _, request, material_ids = _case(n482_package)
    outcome = service.complete(session.id, request)
    assert outcome.breakAndReturn.model_dump() == {
        "breakRequests": 1, "breaksDelivered": 1, "returnedAfterBreak": 1,
    }
    assert len(outcome.generalization.contextsAttempted) == 3
    assert len(outcome.generalization.contextsSuccessful) == 3
    assert material_ids["break_card"] in outcome.materials.usedMaterialIds
    assert material_ids["data_sheet"] in outcome.materials.helpfulMaterialIds
    assert set(outcome.materials.usedMaterialIds).isdisjoint(outcome.materials.unusedMaterialIds)


@pytest.mark.parametrize("change, message", [
    ({"outcome": "no_response", "responseMode": "speech"}, "no-response"),
    ({"outcome": "independent_success", "responseMode": "speech", "promptLevel": "visual"}, "independent success"),
    ({"outcome": "prompted_success", "responseMode": "AAC", "promptLevel": "independent"}, "prompted success"),
    ({"breakRequested": False, "breakDelivered": True, "note": ""}, "explanatory note"),
    ({"breakRequested": False, "breakDelivered": False, "returnedAfterBreak": True}, "no break"),
])
def test_contradictory_trial_validation(change, message):
    raw = {
        "trialId": "trial-1", "opportunityNumber": 1,
        "contextId": "context-1", "contextLabel": "Transition", "valid": True,
        "outcome": "incorrect", "responseMode": "none", "promptLevel": "visual",
        "latencySeconds": None, "breakRequested": False, "breakDelivered": False,
        "returnedAfterBreak": None, "materialIdsUsed": [], "note": "",
    }
    with pytest.raises(SchemaValidationError, match=message):
        SessionTrialObservation.model_validate({**raw, **change})


def test_goal_and_material_mismatch_are_rejected(n482_package):
    _, service, session, _, request, _ = _case(n482_package)
    with pytest.raises(ConflictError, match="goal"):
        service.complete(session.id, request.model_copy(update={"expectedGoalId": "wrong-goal"}))

    _, service, session, _, request, _ = _case(n482_package)
    bad_trial = request.trials[0].model_copy(update={"materialIdsUsed": ["foreign-material"]})
    with pytest.raises(ValidationError, match="outside the session package"):
        service.complete(session.id, request.model_copy(update={"trials": [bad_trial, *request.trials[1:]]}))


def test_historical_revision_snapshot_does_not_change(n482_package):
    repos, service, session, _, request, _ = _case(n482_package)
    outcome = service.complete(session.id, request)
    package = repos.lesson_packages.get(n482_package.id)
    changed_spec = package.lessonSpec.model_copy(update={
        "revision": package.lessonSpec.revision + 1,
        "goal": package.lessonSpec.goal.model_copy(update={"observable_behavior": "A later changed goal"}),
    })
    repos.lesson_packages.save(package.model_copy(update={"lessonSpec": changed_spec}))
    historical = service.for_session(session.id)
    assert historical.goalRevision == outcome.goalRevision
    assert historical.operationalizedGoal == outcome.operationalizedGoal
    assert historical.lessonPackageRevision == outcome.lessonPackageRevision


def test_session_outcome_persists_across_repository_reload(tmp_path, n482_package):
    engine, factory, repository = _repository(f"sqlite:///{tmp_path / 'outcomes.db'}")
    _, service, session, _, request, _ = _case(n482_package, repository)
    saved = service.complete(session.id, request)
    restarted = SQLAlchemyV2Repositories(
        factory,
        repository.config,
        organization_external_id="org-one",
        user_external_id="teacher-one",
        seed_synthetic=False,
    )
    loaded = V2SessionOutcomeService(restarted).for_session(session.id)
    assert loaded.model_dump(mode="json") == saved.model_dump(mode="json")
    assert restarted.sessions.get(session.id).status == "completed"
    engine.dispose()


def test_session_completion_api_contract(monkeypatch, n482_package):
    _, service, session, template, request, _ = _case(n482_package)
    monkeypatch.setattr(v2_routes, "V2SessionOutcomeService", lambda: service)
    client = TestClient(app)
    template_response = client.get(f"/api/v2/sessions/{session.id}/completion-template")
    assert template_response.status_code == 200
    assert template_response.json()["dataSheetColumns"] == template.dataSheetColumns
    response = client.post(
        f"/api/v2/sessions/{session.id}/complete",
        json=request.model_dump(mode="json", by_alias=True),
    )
    assert response.status_code == 201
    assert response.json()["responses"]["promptedSuccessful"] == 3
    assert client.get(f"/api/v2/sessions/{session.id}/outcome").status_code == 200
    learner_outcomes = client.get("/api/v2/learners/n482/session-outcomes")
    assert learner_outcomes.status_code == 200
    assert learner_outcomes.json()[0]["sessionId"] == session.id


def test_session_cannot_bypass_outcome_validation_by_creating_completed_status():
    with pytest.raises(ValidationError, match="Start Session"):
        V2SessionService(V2Repositories()).create(SessionCreate(
            learnerId="a102", goal="Ask for help", status="completed"
        ))
