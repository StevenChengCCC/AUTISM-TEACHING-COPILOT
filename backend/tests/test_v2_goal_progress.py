from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api import v2_routes
from app.main import app
from app.schemas.v2_dto import CompleteSessionRequest, SessionCreate, SessionTrialObservation, SessionUseSnapshot
from app.services.v2_goal_progress_service import V2GoalProgressService
from app.services.v2_instructional_constraint_service import build_instructional_constraint_snapshot
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories
from app.services.v2_session_outcome_service import V2SessionOutcomeService
from app.services.v2_session_service import V2SessionService
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories
from test_v2_lesson_spec import n482_draft, n482_learner
from test_v2_sqlalchemy_persistence import _repository


@pytest.fixture(scope="module")
def n482_package_for_progress():
    repos = V2Repositories()
    learner = n482_learner()
    repos.learners.save(learner)
    snapshot = build_instructional_constraint_snapshot(learner, [])
    draft = n482_draft(snapshot)
    packages = V2LessonPackageService(repos)
    plan = packages.preview_content_plan(draft)
    return packages.generate_product(draft.model_copy(update={"packageContentPlan": plan}))


def _persist_n482_series(repos, package, counts=(1, 2, 3, 4)):
    if repos.learners.get("n482") is None:
        repos.learners.save(n482_learner())
    if repos.lesson_packages.get(package.id) is None:
        repos.lesson_packages.save(package.model_copy(deep=True))
    contexts = package.lessonSpec.contexts
    material_id = package.materials[0].id
    started = datetime(2026, 8, 1, 9, tzinfo=timezone.utc)
    outcomes = []
    independent_positions = (
        {0},
        {0, 1},
        {0, 1, 3},
        {0, 1, 2, 3},
    )
    for session_index, independent_count in enumerate(counts):
        session = V2SessionService(repos).create(SessionCreate(
            learnerId="n482",
            goal=package.goal,
            status="planned",
            lessonPackageId=package.id,
            idempotencyKey=f"n482-progress-session-{session_index + 1}",
        ))
        spec = package.lessonSpec
        use_snapshot = SessionUseSnapshot(
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
            plannedOpportunities=5, startedAt=started,
            startedByTeacher="test-teacher", idempotencyKey=f"start-{session.id}",
        )
        session = repos.sessions.save(session.model_copy(update={"status": "in_progress", "use_snapshot": use_snapshot, "started_at": started}))
        trials = []
        for trial_index in range(5):
            independent = (
                trial_index in independent_positions[session_index]
                if session_index < len(independent_positions)
                and independent_count == session_index + 1
                else trial_index < independent_count
            )
            context = contexts[trial_index % len(contexts)]
            trials.append(SessionTrialObservation(
                trialId=f"{session.id}-trial-{trial_index + 1}",
                opportunityNumber=trial_index + 1,
                contextId=context.id,
                contextLabel=context.label,
                valid=True,
                outcome="independent_success" if independent else "prompted_success",
                responseMode="speech" if independent else "AAC",
                promptLevel="independent" if independent else "visual",
                latencySeconds=5,
                breakRequested=trial_index == 0,
                breakDelivered=trial_index == 0,
                returnedAfterBreak=True if trial_index == 0 else None,
                materialIdsUsed=[material_id],
                note="Synthetic N-482 progress fixture",
            ))
        session_started = started + timedelta(days=session_index * 7)
        outcomes.append(V2SessionOutcomeService(repos).complete(
            session.id,
            CompleteSessionRequest(
                expectedLessonPackageId=package.id,
                expectedLessonSpecId=package.lessonSpec.id,
                expectedGoalId=V2SessionOutcomeService.goal_id(package.lessonSpec),
                startedAt=session_started,
                completedAt=session_started + timedelta(minutes=25),
                trials=trials,
                observations={"teacherNotes": f"Session {session_index + 1}"},
            ),
        ))
    return outcomes


def test_n482_persisted_independent_rate_series_is_20_40_60_80(n482_package_for_progress):
    repos = V2Repositories()
    _persist_n482_series(repos, n482_package_for_progress)
    series = V2GoalProgressService(repos).series("n482")
    assert [point.value for point in series.points] == [20.0, 40.0, 60.0, 80.0]
    assert [point.validOpportunityCount for point in series.points] == [5, 5, 5, 5]
    assert [point.numeratorCount for point in series.points] == [1, 2, 3, 4]
    assert series.latestValue == 80.0
    assert series.trend == "improving"
    assert any("not line slope alone" in item for item in series.trendEvidence)


def test_invalid_trials_are_excluded_and_low_confidence_is_retained(n482_package_for_progress):
    repos = V2Repositories()
    outcomes = _persist_n482_series(repos, n482_package_for_progress, counts=(1,))
    outcome = outcomes[0]
    kept = outcome.trials[:2]
    cancelled = outcome.trials[2].model_copy(update={
        "valid": False, "outcome": "cancelled", "responseMode": "none",
        "promptLevel": "independent", "latencySeconds": None,
        "breakRequested": False, "breakDelivered": False,
        "returnedAfterBreak": None,
    })
    revised = outcome.model_copy(update={
        "opportunities": outcome.opportunities.model_copy(update={"valid": 2, "cancelled": 3}),
        "responses": outcome.responses.model_copy(update={
            "independentSuccessful": 1, "promptedSuccessful": 1,
        }),
        "trials": [*kept, cancelled, cancelled.model_copy(update={"trialId": "cancel-2", "opportunityNumber": 4}), cancelled.model_copy(update={"trialId": "cancel-3", "opportunityNumber": 5})],
    })
    repos.session_outcomes.save(revised)
    point = V2GoalProgressService(repos).series("n482").points[0]
    assert point.value == 50.0
    assert point.validOpportunityCount == 2
    assert point.confidence == "low"
    assert "fewer than three" in point.confidenceReason


def test_zero_one_and_two_session_states(n482_package_for_progress):
    empty = V2GoalProgressService(V2Repositories()).series("n482")
    assert empty.trend == "no_data"
    assert "No completed sessions" in empty.trendEvidence[0]

    one_repo = V2Repositories()
    _persist_n482_series(one_repo, n482_package_for_progress, counts=(1,))
    one = V2GoalProgressService(one_repo).series("n482")
    assert one.trend == "insufficient_data"
    assert "One observation" in one.trendEvidence[0]

    two_repo = V2Repositories()
    _persist_n482_series(two_repo, n482_package_for_progress, counts=(1, 2))
    two = V2GoalProgressService(two_repo).series("n482")
    assert two.trend == "comparison_only"
    assert "Two observations" in two.trendEvidence[0]


def test_goal_separation_and_equivalent_revision_annotation(n482_package_for_progress):
    repos = V2Repositories()
    outcomes = _persist_n482_series(repos, n482_package_for_progress, counts=(1, 2))
    second = outcomes[-1]
    equivalent_revision = second.model_copy(update={
        "id": "outcome-equivalent-revision",
        "sessionId": "session-equivalent-revision",
        "goalRevision": second.goalRevision + 1,
        "completedAt": second.completedAt + timedelta(days=7),
    })
    unrelated = second.model_copy(update={
        "id": "outcome-unrelated-goal",
        "sessionId": "session-unrelated-goal",
        "goalId": "counting-goal",
        "goalRevision": 1,
        "goalComparisonKey": "different-target-and-criterion",
        "operationalizedGoal": "Counts five objects",
        "completedAt": second.completedAt + timedelta(days=8),
    })
    repos.session_outcomes.save(equivalent_revision)
    repos.session_outcomes.save(unrelated)
    service = V2GoalProgressService(repos)
    break_series = service.series("n482", goal_id=second.goalId)
    assert len(break_series.points) == 3
    assert "specification changed" in break_series.points[-1].annotation
    assert all(point.goalId != "counting-goal" for point in break_series.points)
    assert len(service.series_options("n482")) == 2


def test_goal_identity_survives_equivalent_spec_and_changes_with_criterion(n482_package_for_progress):
    spec = n482_package_for_progress.lessonSpec
    equivalent = spec.model_copy(update={"id": "regenerated-equivalent-spec", "revision": spec.revision + 1})
    assert V2SessionOutcomeService.goal_id(equivalent) == V2SessionOutcomeService.goal_id(spec)
    changed_goal = spec.goal.model_copy(update={
        "success_criterion": spec.goal.success_criterion.model_copy(update={"required_successful_opportunities": 5})
    })
    changed = spec.model_copy(update={"goal": changed_goal, "revision": spec.revision + 1})
    assert V2SessionOutcomeService.goal_id(changed) != V2SessionOutcomeService.goal_id(spec)


def test_materially_changed_criterion_creates_historical_series_boundary(n482_package_for_progress):
    repos = V2Repositories()
    outcome = _persist_n482_series(repos, n482_package_for_progress, counts=(1,))[0]
    changed = outcome.model_copy(update={
        "id": "outcome-changed-criterion", "sessionId": "session-changed-criterion",
        "goalRevision": 2, "goalComparisonKey": "changed-success-criterion",
        "completedAt": outcome.completedAt + timedelta(days=7),
    })
    repos.session_outcomes.save(changed)
    service = V2GoalProgressService(repos)
    assert len(service.series_options("n482")) == 2
    historical = service.series("n482", goal_id=outcome.goalId, goal_revision=1)
    current = service.series("n482", goal_id=outcome.goalId, goal_revision=2)
    assert [item.sessionId for item in historical.points] == [outcome.sessionId]
    assert [item.sessionId for item in current.points] == [changed.sessionId]


def test_metric_switching_prompt_transformation_and_point_details(n482_package_for_progress):
    repos = V2Repositories()
    _persist_n482_series(repos, n482_package_for_progress, counts=(1,))
    service = V2GoalProgressService(repos)
    prompt = service.series("n482", metric="prompt_independence_display_score")
    assert prompt.points[0].value == 80.0
    latency = service.series("n482", metric="average_response_latency")
    assert latency.points[0].value == 5.0
    contexts = service.series("n482", metric="generalization_context_count")
    assert contexts.points[0].value == 3.0
    returns = service.series("n482", metric="return_after_break_rate")
    assert returns.points[0].value == 100.0
    point = prompt.points[0]
    assert point.details.promptedSuccessfulCount == 4
    assert point.details.responseModeCounts == {"speech": 1, "AAC": 4, "pointing": 0, "other": 0}
    assert point.details.averageLatencySeconds == 5
    assert point.contextsAttempted
    assert point.details.returnedAfterBreakCount == 1
    assert point.details.materialIdsUsed
    assert point.details.teacherNotes == "Session 1"


def test_progress_series_persists_and_reloads(tmp_path, n482_package_for_progress):
    engine, factory, repository = _repository(f"sqlite:///{tmp_path / 'progress-series.db'}")
    _persist_n482_series(repository, n482_package_for_progress)
    restarted = SQLAlchemyV2Repositories(
        factory,
        repository.config,
        organization_external_id="org-one",
        user_external_id="teacher-one",
        seed_synthetic=False,
    )
    series = V2GoalProgressService(restarted).series("n482")
    assert [point.value for point in series.points] == [20.0, 40.0, 60.0, 80.0]
    engine.dispose()


def test_progress_series_http_contract(monkeypatch, n482_package_for_progress):
    repos = V2Repositories()
    outcomes = _persist_n482_series(repos, n482_package_for_progress)
    service = V2GoalProgressService(repos)
    monkeypatch.setattr(v2_routes, "V2GoalProgressService", lambda: service)
    client = TestClient(app)
    options = client.get("/api/v2/learners/n482/progress-series-options")
    assert options.status_code == 200
    response = client.get(
        "/api/v2/learners/n482/progress-series",
        params={
            "goalId": outcomes[0].goalId,
            "goalRevision": outcomes[0].goalRevision,
            "metric": "independent_success_rate",
        },
    )
    assert response.status_code == 200
    assert [item["value"] for item in response.json()["points"]] == [20.0, 40.0, 60.0, 80.0]
    transit = next(
        item for item in service.series("n482").contextSummaries
        if item.contextLabel.startswith("transit-map")
    )
    filtered = client.get(
        "/api/v2/learners/n482/progress-series",
        params={"goalId": outcomes[0].goalId, "contextKey": transit.contextKey},
    )
    assert filtered.status_code == 200
    assert filtered.json()["activeContextKey"] == transit.contextKey
    assert [item["value"] for item in filtered.json()["points"]] == [50.0, 50.0, 100.0, 100.0]


def test_context_aggregation_percentages_confidence_and_material_usage(n482_package_for_progress):
    repos = V2Repositories()
    _persist_n482_series(repos, n482_package_for_progress)
    series = V2GoalProgressService(repos).series("n482")
    contexts = {item.contextLabel: item for item in series.contextSummaries}

    transit = contexts["transit-map activity to table work"]
    art = contexts["art activity to cleanup"]
    choice = contexts["free choice to shared reading"]
    assert (transit.independentSuccessfulCount, transit.validOpportunityCount, transit.independentSuccessRate) == (6, 8, 75.0)
    assert (art.independentSuccessfulCount, art.validOpportunityCount, art.independentSuccessRate) == (3, 8, 37.5)
    assert (choice.independentSuccessfulCount, choice.validOpportunityCount, choice.independentSuccessRate) == (1, 4, 25.0)
    assert all(item.sessionCount == 4 and item.confidence == "normal" for item in contexts.values())
    assert all(item.filterEligible for item in contexts.values())
    assert transit.transitionFrom == "transit-map activity"
    assert transit.transitionTo == "table work"
    assert transit.evidenceSessionIds == [item.sessionId for item in series.points]

    material = series.materialUsageSummaries[0]
    assert material.sessionCount == 4
    assert material.validOpportunityCount == 20
    assert material.independentSuccessfulCount == 10
    assert material.promptedSuccessfulCount == 10
    assert set(material.contextsWithIndependentResponses) == set(contexts)


def test_context_filter_recalculates_one_goal_curve_from_matching_trials(n482_package_for_progress):
    repos = V2Repositories()
    _persist_n482_series(repos, n482_package_for_progress)
    service = V2GoalProgressService(repos)
    overall = service.series("n482")
    transit = next(item for item in overall.contextSummaries if item.contextLabel.startswith("transit-map"))
    filtered = service.series("n482", context_key=transit.contextKey)

    assert filtered.activeContextKey == transit.contextKey
    assert [item.value for item in filtered.points] == [50.0, 50.0, 100.0, 100.0]
    assert [item.validOpportunityCount for item in filtered.points] == [2, 2, 2, 2]
    assert all(item.contextsAttempted == [transit.contextLabel] for item in filtered.points)
    assert all(item.confidence == "low" for item in filtered.points)
    assert "low confidence" in " ".join(filtered.confidenceReasons).casefold()


def test_context_definition_change_is_not_merged_without_alias(n482_package_for_progress):
    repos = V2Repositories()
    outcome = _persist_n482_series(repos, n482_package_for_progress, counts=(1,))[0]
    changed_trials = [
        trial.model_copy(update={
            "contextLabel": "Transit center to table work",
            "contextSetting": "community transit center",
        }) if trial.contextId == "context-1" else trial
        for trial in outcome.trials
    ]
    changed = outcome.model_copy(update={
        "id": "outcome-context-revision",
        "sessionId": "session-context-revision",
        "goalRevision": outcome.goalRevision + 1,
        "completedAt": outcome.completedAt + timedelta(days=7),
        "trials": changed_trials,
    })
    repos.session_outcomes.save(changed)
    summaries = V2GoalProgressService(repos).series("n482").contextSummaries

    old = next(item for item in summaries if item.contextLabel == "transit-map activity to table work")
    new = next(item for item in summaries if item.contextLabel == "Transit center to table work")
    assert old.contextId == new.contextId == "context-1"
    assert old.contextKey != new.contextKey
    assert old.validOpportunityCount == new.validOpportunityCount == 2


def test_variable_trend_and_missing_measurement_confidence_are_cautious(n482_package_for_progress):
    repos = V2Repositories()
    outcomes = _persist_n482_series(repos, n482_package_for_progress, counts=(1, 4, 1))
    first = outcomes[0]
    no_latency = first.model_copy(update={
        "trials": [trial.model_copy(update={"latencySeconds": None}) for trial in first.trials],
    })
    repos.session_outcomes.save(no_latency)
    series = V2GoalProgressService(repos).series("n482")

    assert series.trend == "variable"
    assert "Performance varied" in series.trendEvidence[0]
    assert not any("regress" in item.casefold() or "master" in item.casefold() for item in series.trendEvidence)
    assert series.confidence == "normal"  # 10 of 15 trials still include latency.


def test_context_summary_low_confidence_explains_sparse_and_missing_data(n482_package_for_progress):
    repos = V2Repositories()
    outcome = _persist_n482_series(repos, n482_package_for_progress, counts=(1,))[0]
    sparse = outcome.model_copy(update={
        "trials": [
            trial.model_copy(update={"latencySeconds": None})
            if trial.contextId == "context-3" else trial
            for trial in outcome.trials
        ],
    })
    repos.session_outcomes.save(sparse)
    summary = next(
        item for item in V2GoalProgressService(repos).series("n482").contextSummaries
        if item.contextId == "context-3"
    )
    assert summary.confidence == "low"
    assert not summary.filterEligible
    assert any("Fewer than two sessions" in item for item in summary.confidenceReasons)
    assert any("Fewer than three valid" in item for item in summary.confidenceReasons)
    assert any("latency" in item for item in summary.confidenceReasons)
