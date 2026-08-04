from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api import v2_routes
from app.core.exceptions import ConflictError, ValidationError, VersionConflictError
from app.main import app
from app.schemas.v2_dto import (
    CompleteSessionRunDraftRequest,
    DiscardSessionRunDraftRequest,
    LessonPackageDecisionRequest,
    PatchSessionRunDraftRequest,
    LessonPackageExportJobDto,
    PrintPackageManifest,
    PrintPackageManifestSection,
    PrintSourceApprovalReadinessEvidence,
    SessionCreate,
    StartSessionRequest,
)
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_print_readiness_service import V2PrintReadinessService
from app.services.v2_repositories import V2Repositories
from app.services.v2_session_run_service import V2SessionRunService
from app.services.v2_session_service import V2SessionService
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories
from test_v2_print_readiness import _generated_package
from test_v2_sqlalchemy_persistence import _repository


def _approved_case(repos=None):
    repos = repos or V2Repositories()
    package = _generated_package(repos)
    materials = V2MaterialService(repos)
    for item in V2LessonPackageService(repos).get_product(package.id).materials:
        current = repos.generated_materials.get(item.id)
        if current.visualAssetPlan:
            for visual in current.visualAssetPlan.visual_items:
                if visual.required and visual.status == "failed":
                    materials.choose_visual_fallback(current.id, visual.id)
                    current = repos.generated_materials.get(item.id)
        materials.review_generated(item.id)
        materials.approve_generated(item.id)
    current = V2LessonPackageService(repos).get_product(package.id)
    package = V2LessonPackageService(repos).approve_product(
        current.id,
        LessonPackageDecisionRequest(
            expectedVersion=current.version, reason="session-run fixture"
        ),
    )
    session = V2SessionService(repos).create(SessionCreate(
        learnerId=package.learnerId,
        goal=package.goal,
        status="planned",
        lessonPackageId=package.id,
    ))
    start = StartSessionRequest(
        idempotencyKey=f"start-{session.id}",
        startedByTeacher="teacher-synthetic",
        expectedPackageRevision=package.version,
        contextIds=[item.id for item in package.lessonSpec.contexts],
    )
    return repos, package, session, start


def _complete_trials(state):
    contexts = state.snapshot.teacherConfirmedContexts
    material_id = next(iter(state.snapshot.materialRevisions))
    return [
        trial.model_copy(update={
            "contextId": contexts[index % len(contexts)].id,
            "contextLabel": contexts[index % len(contexts)].label,
            "valid": True,
            "outcome": "independent_success",
            "responseMode": "speech",
            "promptLevel": "independent",
            "materialIdsUsed": [material_id],
        })
        for index, trial in enumerate(state.draft.trials)
    ]


def test_start_rejects_unapproved_stale_and_not_ready_packages():
    repos, package, session, start = _approved_case()
    stale = start.model_copy(update={"expectedPackageRevision": package.version - 1})
    with pytest.raises(ConflictError, match="changed from revision"):
        V2SessionRunService(repos).start(session.id, stale)

    current = repos.lesson_packages.get(package.id)
    repos.lesson_packages.save(current.model_copy(update={"status": "teacher_review_needed"}))
    with pytest.raises(ConflictError, match="Session cannot start"):
        V2SessionRunService(repos).start(
            session.id,
            start.model_copy(update={"expectedPackageRevision": package.version + 1}),
        )


def test_start_is_idempotent_and_freezes_exact_revisions_without_invented_data():
    repos, package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    first = service.start(session.id, start)
    second = service.start(session.id, start)
    assert second.snapshot == first.snapshot
    assert second.draft == first.draft
    assert first.snapshot.packageRevision == package.version
    assert first.snapshot.lessonSpecRevision == package.lessonSpec.revision
    assert first.snapshot.materialRevisions
    assert all(item.outcome is None for item in first.draft.trials)
    assert all(item.responseMode is None for item in first.draft.trials)
    assert all(item.promptLevel is None for item in first.draft.trials)
    with pytest.raises(ConflictError, match="deliberately new run"):
        service.start(session.id, start.model_copy(update={"idempotencyKey": "new-run"}))


def test_optional_pdf_artifact_lineage_is_frozen():
    repos, package, session, start = _approved_case()
    readiness = V2PrintReadinessService(repos).evaluate(package.id)
    export = LessonPackageExportJobDto(
        exportId="print-kit-session-lineage", learnerId=package.learnerId,
        packageId=package.id, status="completed", format="pdf",
        artifactSha256="a" * 64,
        printPackageManifest=PrintPackageManifest(
            packageId=package.id, packageRevision=package.version,
            lessonSpecId=package.lessonSpec.id,
            lessonSpecRevision=package.lessonSpec.revision,
            profileRevision=package.profileRevision,
            sections=[PrintPackageManifestSection(sectionType="cover", title="Cover")],
            materialRevisions=readiness.materialRevisions,
            generatedAt="2026-08-04T09:00:00Z",
            rendererVersion=readiness.rendererVersion,
            sourceApprovalReadinessEvidence=PrintSourceApprovalReadinessEvidence(
                evaluatedAt=readiness.evaluatedAt,
                ready=True,
                packageApprovalStatus="approved",
                packageRevision=package.version,
                lessonSpecRevision=package.lessonSpec.revision,
                materialReviewedRevisions=readiness.materialRevisions,
                materialApprovedRevisions=readiness.materialRevisions,
            ),
        ),
    )
    repos.export_jobs.save(export)
    state = V2SessionRunService(repos).start(
        session.id,
        start.model_copy(update={
            "pdfExportId": export.exportId, "printPreset": "complete_kit"
        }),
    )
    assert state.snapshot.pdfArtifact.exportId == export.exportId
    assert state.snapshot.pdfArtifact.sha256 == "a" * 64
    assert state.snapshot.pdfArtifact.printPreset == "complete_kit"


def test_later_package_edit_warns_without_mutating_snapshot():
    repos, package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    original = deepcopy(service.start(session.id, start).snapshot)
    current = repos.lesson_packages.get(package.id)
    repos.lesson_packages.save(current.model_copy(update={"lessonBrief": "Later revision"}))
    state = service.state(session.id)
    assert state.packageChanged is True
    assert state.packageChangeWarning
    assert state.snapshot == original


def test_partial_patch_resume_conflict_and_duplicate_retry():
    repos, _package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    trial = state.draft.trials[0].model_copy(update={
        "contextId": state.snapshot.teacherConfirmedContexts[0].id,
        "contextLabel": state.snapshot.teacherConfirmedContexts[0].label,
        "note": "Teacher partial observation",
    })
    request = PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey="patch-one",
        trials=[trial, *state.draft.trials[1:]],
    )
    saved = service.patch(session.id, request)
    assert saved.draft.trials[0].note == "Teacher partial observation"
    assert service.state(session.id).draft == saved.draft
    assert service.patch(session.id, request).draft == saved.draft
    with pytest.raises(VersionConflictError, match="Local input was not overwritten"):
        service.patch(session.id, request.model_copy(update={"idempotencyKey": "stale"}))


def test_snapshot_and_draft_exclude_source_content_and_full_prompts():
    repos, package, session, start = _approved_case()
    assert package.lessonSpec.teacher_request
    V2SessionRunService(repos).start(session.id, start)

    persisted = repos.sessions.get(session.id).model_dump_json(by_alias=True)
    assert package.lessonSpec.teacher_request not in persisted
    assert "sourceExcerpt" not in persisted
    assert "rawRecord" not in persisted


def test_atomic_completion_uses_snapshot_and_completed_data_is_immutable():
    repos, package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    saved = service.patch(session.id, PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey="complete-values",
        status="ready_for_closeout",
        trials=_complete_trials(state),
        generalization={"status": "not_attempted"},
        observations={"teacherNotes": "Exact teacher observation", "rawCountsConfirmed": True},
    ))
    current = repos.lesson_packages.get(package.id)
    repos.lesson_packages.save(current.model_copy(update={"lessonBrief": "Changed after start"}))
    request = CompleteSessionRunDraftRequest(
        expectedVersion=saved.draft.version, idempotencyKey="complete-once"
    )
    outcome = service.complete(session.id, request)
    assert outcome.lessonPackageRevision == state.snapshot.packageRevision
    assert outcome.sessionUseSnapshotId == state.snapshot.id
    assert outcome.sessionUseSnapshot == state.snapshot
    assert outcome.observations.teacherNotes == "Exact teacher observation"
    assert service.state(session.id).draft.status == "completed"
    assert service.complete(session.id, request).id == outcome.id
    with pytest.raises(ConflictError, match="immutable"):
        service.complete(session.id, request.model_copy(update={"idempotencyKey": "again"}))
    with pytest.raises(ConflictError, match="not editable"):
        service.patch(session.id, PatchSessionRunDraftRequest(
            expectedVersion=saved.draft.version + 1,
            idempotencyKey="late-patch",
            observations={"teacherNotes": "overwrite"},
        ))


def test_incomplete_draft_cannot_be_converted_to_final_observations():
    repos, _package, session, start = _approved_case()
    state = V2SessionRunService(repos).start(session.id, start)
    with pytest.raises(ValidationError, match="is incomplete"):
        V2SessionRunService(repos).complete(session.id, CompleteSessionRunDraftRequest(
            expectedVersion=state.draft.version, idempotencyKey="incomplete"
        ))


def test_discard_is_explicit_retained_and_not_editable():
    repos, _package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    discarded = service.discard(session.id, DiscardSessionRunDraftRequest(
        expectedVersion=state.draft.version, idempotencyKey="discard", confirmed=True
    ))
    assert discarded.draft.status == "discarded"
    assert service.state(session.id).draft.status == "discarded"
    with pytest.raises(ConflictError, match="no longer editable"):
        service.patch(session.id, PatchSessionRunDraftRequest(
            expectedVersion=discarded.draft.version,
            idempotencyKey="after-discard",
            observations={"teacherNotes": "should not save"},
        ))


def test_sql_restart_restores_exact_snapshot_and_partial_draft(tmp_path):
    engine, factory, repository = _repository(f"sqlite:///{tmp_path / 'session-runs.db'}")
    repos, _package, session, start = _approved_case(repository)
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    saved = service.patch(session.id, PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey="restart-save",
        activeTrialNumber=3,
        trials=[state.draft.trials[0].model_copy(update={"note": "survives restart"}), *state.draft.trials[1:]],
    ))
    restarted = SQLAlchemyV2Repositories(
        factory, repository.config, organization_external_id="org-one",
        user_external_id="teacher-one", seed_synthetic=False,
    )
    loaded = V2SessionRunService(restarted).state(session.id)
    assert loaded.snapshot == saved.snapshot
    assert loaded.draft == saved.draft
    assert loaded.draft.activeTrialNumber == 3
    engine.dispose()


def test_drafts_are_not_progress_or_recommendation_evidence():
    repos, package, session, start = _approved_case()
    state = V2SessionRunService(repos).start(session.id, start)
    V2SessionRunService(repos).patch(session.id, PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey="draft-only",
        trials=_complete_trials(state),
    ))
    assert repos.session_outcomes.list() == []
    from app.services.v2_goal_progress_service import V2GoalProgressService
    assert V2GoalProgressService(repos).series_options(package.learnerId) == []


def test_mixed_recorder_paths_preserve_closeout_evidence_and_exclude_invalid_trials():
    repos, package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    contexts = state.snapshot.teacherConfirmedContexts
    material_ids = list(state.snapshot.materialRevisions)
    trials = [
        state.draft.trials[0].model_copy(update={
            "contextId": contexts[0].id, "contextLabel": contexts[0].label,
            "valid": True, "outcome": "independent_success",
            "responseMode": "speech", "promptLevel": None,
        }),
        state.draft.trials[1].model_copy(update={
            "contextId": contexts[1].id, "contextLabel": contexts[1].label,
            "valid": True, "outcome": "prompted_success",
            "responseMode": "AAC", "promptLevel": "visual",
        }),
        state.draft.trials[2].model_copy(update={
            "contextId": contexts[2].id, "contextLabel": contexts[2].label,
            "valid": True, "outcome": "not_observed_unsuccessful",
        }),
        state.draft.trials[3].model_copy(update={
            "contextId": contexts[0].id, "contextLabel": contexts[0].label,
            "valid": True, "outcome": "break_honored",
            "breakRequested": True, "breakDelivered": True,
            "returnedAfterBreak": False,
        }),
        state.draft.trials[4].model_copy(update={
            "contextId": contexts[1].id, "contextLabel": contexts[1].label,
            "valid": False, "outcome": "cancelled",
            "note": "Transition was interrupted by a school announcement.",
        }),
    ]
    saved = service.patch(session.id, PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey="mixed-recorder-closeout",
        status="ready_for_closeout",
        activeTrialNumber=4,
        trials=trials,
        generalization={"status": "observed", "settings": ["classroom"]},
        helpfulMaterialIds=[material_ids[0]],
        unhelpfulMaterialIds=[material_ids[1]],
        observations={
            "engagementLevel": 3, "regulationLevel": 2,
            "teacherNotes": "Teacher-authored closeout evidence.",
            "rawCountsConfirmed": True,
        },
    ))
    assert service.state(session.id).draft.activeTrialNumber == 4
    outcome = service.complete(session.id, CompleteSessionRunDraftRequest(
        expectedVersion=saved.draft.version, idempotencyKey="mixed-complete"
    ))

    assert outcome.opportunities.valid == 4
    assert outcome.opportunities.cancelled == 1
    assert outcome.responses.independentSuccessful == 1
    assert outcome.responses.promptedSuccessful == 1
    assert outcome.responses.notObservedOrUnsuccessful == 1
    assert outcome.responses.breakOrStopHonored == 1
    assert outcome.prompting.promptLevelCounts == {"visual": 1}
    assert outcome.breakAndReturn.breaksDelivered == 1
    assert outcome.generalization.status == "observed"
    assert outcome.materials.helpfulMaterialIds == [material_ids[0]]
    assert outcome.materials.unhelpfulMaterialIds == [material_ids[1]]
    assert outcome.observations.rawCountsConfirmed is True
    assert outcome.trials[0].promptLevel is None

    from app.services.v2_goal_progress_service import V2GoalProgressService
    series = V2GoalProgressService(repos).series(
        package.learnerId, goal_id=outcome.goalId, goal_revision=outcome.goalRevision
    )
    assert series.points[0].validOpportunityCount == 4
    assert series.points[0].value == 25.0


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"valid": True, "outcome": "prompted_success", "responseMode": "AAC"}, "prompt level"),
        ({"valid": False, "outcome": "cancelled"}, "validity reason"),
        ({"valid": True, "outcome": "break_honored", "breakRequested": True,
          "breakDelivered": True}, "return status"),
    ],
)
def test_progressive_result_paths_report_exact_missing_fields(updates, message):
    repos, _package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    context = state.snapshot.teacherConfirmedContexts[0]
    trial = state.draft.trials[0].model_copy(update={
        "contextId": context.id, "contextLabel": context.label, **updates,
    })
    trials = [trial, *_complete_trials(state)[1:]]
    saved = service.patch(session.id, PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey=f"missing-{message}",
        trials=trials,
        observations={"rawCountsConfirmed": True},
    ))
    with pytest.raises(ValidationError, match=message):
        service.complete(session.id, CompleteSessionRunDraftRequest(
            expectedVersion=saved.draft.version, idempotencyKey="reject-incomplete"
        ))


def test_raw_count_confirmation_is_a_closeout_gate():
    repos, _package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    saved = service.patch(session.id, PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey="complete-without-confirmation",
        trials=_complete_trials(state),
    ))
    with pytest.raises(ValidationError, match="valid and invalid opportunity counts"):
        service.complete(session.id, CompleteSessionRunDraftRequest(
            expectedVersion=saved.draft.version, idempotencyKey="blocked-closeout"
        ))


def test_generalization_status_requires_an_explicit_closeout_choice():
    repos, _package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    state = service.start(session.id, start)
    assert state.draft.generalization.status is None
    saved = service.patch(session.id, PatchSessionRunDraftRequest(
        expectedVersion=state.draft.version,
        idempotencyKey="complete-without-generalization-choice",
        trials=_complete_trials(state),
        observations={"rawCountsConfirmed": True},
    ))
    with pytest.raises(ValidationError, match="Choose whether generalization"):
        service.complete(session.id, CompleteSessionRunDraftRequest(
            expectedVersion=saved.draft.version,
            idempotencyKey="blocked-generalization-closeout",
        ))


def test_digital_coding_snapshot_matches_printable_data_sheet():
    repos, package, session, start = _approved_case()
    state = V2SessionRunService(repos).start(session.id, start)
    data_sheet = next(item for item in package.materials if item.type == "data_sheet")
    content = data_sheet.materialSpec.content
    assert state.snapshot.independenceDefinition == content.independence_rule
    assert state.snapshot.dataMeasures == content.exact_columns
    assert state.snapshot.promptLevelDefinitions == content.prompt_level_definitions


def test_session_run_api_start_patch_resume_and_complete(monkeypatch):
    repos, _package, session, start = _approved_case()
    service = V2SessionRunService(repos)
    monkeypatch.setattr(v2_routes, "V2SessionRunService", lambda: service)
    client = TestClient(app)
    started = client.post(
        f"/api/v2/sessions/{session.id}/start",
        json=start.model_dump(mode="json", by_alias=True),
    )
    assert started.status_code == 200
    state = service.state(session.id)
    patched = client.patch(
        f"/api/v2/sessions/{session.id}/run-draft",
        json=PatchSessionRunDraftRequest(
            expectedVersion=state.draft.version,
            idempotencyKey="api-patch",
            trials=_complete_trials(state),
            generalization={"status": "not_attempted"},
            observations={"rawCountsConfirmed": True},
        ).model_dump(mode="json", by_alias=True),
    )
    assert patched.status_code == 200
    assert client.get(f"/api/v2/sessions/{session.id}/run").status_code == 200
    completed = client.post(
        f"/api/v2/sessions/{session.id}/run-draft/complete",
        json={
            "expectedVersion": patched.json()["draft"]["version"],
            "idempotencyKey": "api-complete",
        },
    )
    assert completed.status_code == 201
    assert completed.json()["sessionUseSnapshotId"] == started.json()["snapshot"]["id"]
