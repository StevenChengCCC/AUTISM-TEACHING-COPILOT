from __future__ import annotations

from hashlib import sha256
import json

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
    VersionConflictError,
)
from app.core.auth_context import get_authenticated_scope
from app.schemas.v2_dto import (
    CompleteSessionRequest,
    CompleteSessionRunDraftRequest,
    DiscardSessionRunDraftRequest,
    LessonPackageDto,
    LessonPackageExportJobDto,
    GoalSpecificDataSheetSpec,
    LessonSession,
    PatchSessionRunDraftRequest,
    SessionPdfArtifactLineage,
    SessionRunDraft,
    SessionRunDraftTrial,
    SessionRunStateDto,
    SessionTrialObservation,
    SessionUseSnapshot,
    SessionVisualPlanRevision,
    StartSessionRequest,
    utc_now,
)
from app.services.v2_print_readiness_service import V2PrintReadinessService
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_session_outcome_service import V2SessionOutcomeService


def _payload_hash(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude={"expectedVersion"})
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class V2SessionRunService:
    """Revision-frozen classroom session run and durable autosave boundary."""

    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos

    def start(self, session_id: str, request: StartSessionRequest) -> SessionRunStateDto:
        session = self._session(session_id)
        if session.use_snapshot is not None:
            if session.use_snapshot.idempotencyKey == request.idempotencyKey:
                return self.state(session_id)
            raise ConflictError(
                "This session already has a frozen classroom run. Duplicate the session to start a deliberately new run."
            )
        if session.status not in {"planned", "draft"}:
            raise ConflictError("Only a planned session can be started")
        package = self._package(session)
        if package.version != request.expectedPackageRevision:
            raise ConflictError(
                f"The lesson package changed from revision {request.expectedPackageRevision} to {package.version}. Review the current package before starting."
            )
        readiness = V2PrintReadinessService(self.repos).evaluate(package.id)
        if not readiness.ready:
            blocker = next(item for item in readiness.blockers if item.severity == "blocking")
            raise ConflictError(
                f"Session cannot start: {blocker.explanation} Recovery action: {blocker.recoveryAction}."
            )
        if package.status != "approved" or package.lessonSpec is None:
            raise ConflictError("Session cannot start until the current package is approved")

        spec = package.lessonSpec
        by_context = {item.id: item for item in spec.contexts}
        if len(request.contextIds) != len(set(request.contextIds)):
            raise ValidationError("Teacher-confirmed session contexts must be unique")
        unknown_contexts = set(request.contextIds) - set(by_context)
        if unknown_contexts:
            raise ValidationError("A teacher-confirmed context is not part of the current LessonSpec")
        contexts = [by_context[item] for item in request.contextIds]
        if not contexts:
            raise ValidationError("Confirm at least one classroom context before starting")

        materials = V2PrintReadinessService(self.repos).current_materials(package)
        visual_revisions = [
            SessionVisualPlanRevision(
                planId=f"visual-plan:{item.id}:r{item.visualAssetPlan.material_revision}",
                materialId=item.id,
                revision=item.visualAssetPlan.material_revision,
            )
            for item in materials
            if item.visualAssetPlan is not None
        ]
        artifact = self._pdf_lineage(package, request)
        data_sheet = next(
            (
                item.materialSpec.content for item in materials
                if isinstance(item.materialSpec, GoalSpecificDataSheetSpec)
            ),
            None,
        )
        planned = (
            spec.goal.success_criterion.total_opportunities
            if spec.goal.success_criterion and spec.goal.success_criterion.total_opportunities
            else max(1, len(contexts))
        )
        now = utc_now()
        authenticated = get_authenticated_scope()
        snapshot = SessionUseSnapshot(
            id=f"use-{session.id}-{sha256(request.idempotencyKey.encode()).hexdigest()[:12]}",
            sessionId=session.id,
            learnerId=session.learner_id,
            goalId=V2SessionOutcomeService.goal_id(spec),
            goalRevision=spec.revision,
            goalComparisonKey=V2SessionOutcomeService.goal_comparison_key(spec),
            operationalizedGoal=spec.goal.observable_behavior,
            lessonSpecId=spec.id,
            lessonSpecRevision=spec.revision,
            packageId=package.id,
            packageRevision=package.version,
            materialRevisions=readiness.materialRevisions,
            materialLabels={item.id: item.title for item in materials},
            visualPlanRevisions=visual_revisions,
            pdfArtifact=artifact,
            teacherConfirmedContexts=contexts,
            acceptedResponseModes=list(spec.communication_plan.accepted_modes or spec.goal.accepted_response_modes),
            promptLevelDefinitions=(
                list(data_sheet.prompt_level_definitions)
                if data_sheet else list(spec.data_plan.prompt_levels)
            ),
            independenceDefinition=(
                data_sheet.independence_rule if data_sheet
                else (spec.data_plan.independence_definition or spec.goal.independence_definition)
            ),
            dataMeasures=list(spec.data_plan.measures),
            plannedOpportunities=planned,
            startedAt=now,
            startedByTeacher=(authenticated.user_external_id if authenticated else request.startedByTeacher),
            idempotencyKey=request.idempotencyKey,
        )
        draft = SessionRunDraft(
            id=f"run-draft-{session.id}",
            sessionId=session.id,
            snapshotId=snapshot.id,
            trials=[
                SessionRunDraftTrial(
                    trialId=f"{session.id}-trial-{index}", opportunityNumber=index
                )
                for index in range(1, planned + 1)
            ],
            lastSavedAt=now,
        )
        self.repos.sessions.save(session.model_copy(update={
            "status": "in_progress",
            "lesson_package_revision": snapshot.packageRevision,
            "lesson_spec_id": snapshot.lessonSpecId,
            "goal_id": snapshot.goalId,
            "goal_revision": snapshot.goalRevision,
            "operationalized_goal": snapshot.operationalizedGoal,
            "started_at": now,
            "use_snapshot": snapshot,
            "run_draft": draft,
            "updated_at": now,
        }))
        return self.state(session_id)

    def state(self, session_id: str) -> SessionRunStateDto:
        session = self._session(session_id)
        if session.use_snapshot is None or session.run_draft is None:
            raise NotFoundError("This session has not been started")
        changed = self._package_changed(session.use_snapshot)
        return SessionRunStateDto(
            snapshot=session.use_snapshot,
            draft=session.run_draft,
            packageChanged=changed,
            packageChangeWarning=(
                "The lesson package has changed since this session started. This run remains bound to its frozen revisions."
                if changed else None
            ),
        )

    def patch(self, session_id: str, request: PatchSessionRunDraftRequest) -> SessionRunStateDto:
        session = self._active_session(session_id)
        draft = session.run_draft
        assert draft is not None
        mutation_hash = _payload_hash(request)
        if draft.lastMutationIdempotencyKey == request.idempotencyKey:
            if draft.lastMutationHash != mutation_hash:
                raise ConflictError("The draft idempotency key was reused for different teacher input")
            return self.state(session_id)
        if request.expectedVersion != draft.version:
            raise VersionConflictError(
                f"The session draft changed from version {request.expectedVersion} to {draft.version}. Local input was not overwritten."
            )
        updates = {
            key: value for key, value in {
                "status": request.status,
                "trials": request.trials,
                "generalization": request.generalization,
                "helpfulMaterialIds": request.helpfulMaterialIds,
                "unhelpfulMaterialIds": request.unhelpfulMaterialIds,
                "observations": request.observations,
                "activeTrialNumber": request.activeTrialNumber,
            }.items() if value is not None
        }
        candidate = draft.model_copy(update={
            **updates,
            "lastSavedAt": utc_now(),
            "lastMutationIdempotencyKey": request.idempotencyKey,
            "lastMutationHash": mutation_hash,
            "version": draft.version + 1,
        })
        self._validate_partial(session.use_snapshot, candidate)
        saved_session = self.repos.sessions.save(session.model_copy(update={
            "run_draft": candidate,
            "updated_at": utc_now(),
        }))
        assert saved_session.run_draft is not None
        return self.state(saved_session.id)

    def discard(self, session_id: str, request: DiscardSessionRunDraftRequest) -> SessionRunStateDto:
        session = self._active_session(session_id)
        draft = session.run_draft
        assert draft is not None
        if request.expectedVersion != draft.version:
            raise VersionConflictError("The session draft changed before discard; reload before confirming discard")
        discarded = draft.model_copy(update={
            "status": "discarded",
            "lastSavedAt": utc_now(),
            "lastMutationIdempotencyKey": request.idempotencyKey,
            "lastMutationHash": _payload_hash(request),
            "version": draft.version + 1,
        })
        self.repos.sessions.save(session.model_copy(update={
            "status": "draft", "run_draft": discarded, "updated_at": utc_now()
        }))
        return self.state(session_id)

    def complete(self, session_id: str, request: CompleteSessionRunDraftRequest):
        session = self._session(session_id)
        draft = session.run_draft
        snapshot = session.use_snapshot
        if draft is None or snapshot is None:
            raise ConflictError("Start the session before completing observations")
        existing = V2SessionOutcomeService(self.repos).for_session(session_id, required=False)
        if draft.status == "completed" and existing is not None:
            if draft.completionIdempotencyKey == request.idempotencyKey:
                return existing
            raise ConflictError("This session already has a completed immutable outcome")
        if draft.status == "discarded":
            raise ConflictError("A discarded session draft cannot be completed")
        if request.expectedVersion != draft.version:
            raise VersionConflictError("The session draft changed before completion; reload before closing out")
        self._validate_partial(snapshot, draft)
        trials = [self._final_trial(item) for item in draft.trials]
        if not draft.observations.rawCountsConfirmed:
            raise ValidationError("Confirm the displayed valid and invalid opportunity counts before completion")
        if draft.generalization.status is None:
            raise ValidationError(
                "Choose whether generalization was observed, not observed, or not attempted"
            )
        payload = CompleteSessionRequest(
            expectedLessonPackageId=snapshot.packageId,
            expectedLessonSpecId=snapshot.lessonSpecId,
            expectedGoalId=snapshot.goalId,
            startedAt=snapshot.startedAt,
            completedAt=utc_now(),
            trials=trials,
            generalization={
                "status": draft.generalization.status,
                "people": draft.generalization.people,
                "settings": draft.generalization.settings,
                "materials": draft.generalization.materials,
            },
            helpfulMaterialIds=draft.helpfulMaterialIds,
            unhelpfulMaterialIds=draft.unhelpfulMaterialIds,
            observations=draft.observations,
        )
        return V2SessionOutcomeService(self.repos).complete(
            session_id,
            payload,
            draft_completion_idempotency_key=request.idempotencyKey,
        )

    def _validate_partial(self, snapshot: SessionUseSnapshot | None, draft: SessionRunDraft) -> None:
        if snapshot is None:
            raise ConflictError("The session-use snapshot is missing")
        ids = [item.trialId for item in draft.trials]
        numbers = [item.opportunityNumber for item in draft.trials]
        if len(ids) != len(set(ids)) or len(numbers) != len(set(numbers)):
            raise ValidationError("Draft trial IDs and opportunity numbers must be unique")
        if len(draft.trials) != snapshot.plannedOpportunities:
            raise ValidationError("The draft must retain every planned opportunity slot")
        if draft.activeTrialNumber > snapshot.plannedOpportunities:
            raise ValidationError("The active trial must be one of the frozen opportunity slots")
        context_ids = {item.id for item in snapshot.teacherConfirmedContexts}
        material_ids = set(snapshot.materialRevisions)
        for trial in draft.trials:
            if trial.contextId is not None and trial.contextId not in context_ids:
                raise ValidationError("A draft trial references a context outside the frozen session snapshot")
            if set(trial.materialIdsUsed) - material_ids:
                raise ValidationError("A draft trial references material outside the frozen session snapshot")
        if set(draft.helpfulMaterialIds + draft.unhelpfulMaterialIds) - material_ids:
            raise ValidationError("Draft material feedback references material outside the frozen session snapshot")
        if set(draft.helpfulMaterialIds) & set(draft.unhelpfulMaterialIds):
            raise ValidationError("A material cannot be both helpful and unhelpful")

    @staticmethod
    def _final_trial(item: SessionRunDraftTrial) -> SessionTrialObservation:
        required = [
            ("context", item.contextId), ("validity", item.valid),
            ("outcome", item.outcome),
        ]
        if item.outcome in {"independent_success", "prompted_success"}:
            required.append(("response mode", item.responseMode))
        if item.outcome == "prompted_success":
            required.append(("prompt level", item.promptLevel))
        if item.outcome == "cancelled" and not item.note.strip():
            required.append(("validity reason", None))
        if item.outcome == "break_honored":
            required.extend([
                ("break requested status", item.breakRequested),
                ("break delivered status", item.breakDelivered),
                ("return status", item.returnedAfterBreak),
            ])
        missing = [label for label, value in required if value is None]
        if missing:
            raise ValidationError(
                f"Opportunity {item.opportunityNumber} is incomplete: {', '.join(missing)}"
            )
        return SessionTrialObservation(
            trialId=item.trialId,
            opportunityNumber=item.opportunityNumber,
            contextId=item.contextId,
            contextLabel=item.contextLabel or item.contextId,
            valid=item.valid,
            outcome=item.outcome,
            responseMode=item.responseMode or "none",
            promptLevel=item.promptLevel,
            latencySeconds=item.latencySeconds,
            breakRequested=bool(item.breakRequested),
            breakDelivered=bool(item.breakDelivered),
            returnedAfterBreak=item.returnedAfterBreak,
            materialIdsUsed=item.materialIdsUsed,
            note=item.note,
        )

    def _pdf_lineage(
        self, package: LessonPackageDto, request: StartSessionRequest
    ) -> SessionPdfArtifactLineage | None:
        if request.pdfExportId is None:
            return None
        export = self.repos.export_jobs.get(request.pdfExportId)
        if not isinstance(export, LessonPackageExportJobDto) or export.status != "completed":
            raise ConflictError("The selected PDF artifact is not ready")
        manifest = export.printPackageManifest
        if export.packageId != package.id or manifest is None:
            raise ConflictError("The selected PDF artifact belongs to a different package")
        if manifest.packageRevision != package.version:
            raise ConflictError("The selected PDF artifact uses a stale package revision")
        if request.printPreset is not None and request.printPreset != manifest.printPreset:
            raise ConflictError("The selected print preset does not match the PDF manifest")
        if not export.artifactSha256:
            raise ConflictError("The selected PDF artifact is missing its integrity hash")
        return SessionPdfArtifactLineage(
            exportId=export.exportId,
            manifestVersion=manifest.schemaVersion,
            rendererVersion=manifest.rendererVersion,
            printPreset=manifest.printPreset,
            pageSize=manifest.pageSize,
            textProfile=manifest.textProfile,
            sha256=export.artifactSha256,
        )

    def _package_changed(self, snapshot: SessionUseSnapshot) -> bool:
        package = self.repos.lesson_packages.get(snapshot.packageId)
        if not isinstance(package, LessonPackageDto):
            return True
        if package.version != snapshot.packageRevision:
            return True
        current = V2PrintReadinessService(self.repos).current_materials(package)
        revisions = {
            item.id: item.materialSpec.revision if item.materialSpec else item.version
            for item in current
        }
        return revisions != snapshot.materialRevisions

    def _active_session(self, session_id: str) -> LessonSession:
        session = self._session(session_id)
        if session.status == "completed" or session.run_draft is None:
            raise ConflictError("This session run is not editable")
        if session.run_draft.status in {"completed", "discarded"}:
            raise ConflictError("This session draft is no longer editable")
        return session

    def _session(self, session_id: str) -> LessonSession:
        session = self.repos.sessions.get(session_id)
        if not isinstance(session, LessonSession):
            raise NotFoundError("Lesson session not found")
        return session

    def _package(self, session: LessonSession) -> LessonPackageDto:
        if not session.lesson_package_id:
            raise ValidationError("Link an approved lesson package before starting the session")
        package = self.repos.lesson_packages.get(session.lesson_package_id)
        if not isinstance(package, LessonPackageDto):
            raise NotFoundError("Session lesson package not found")
        if package.learnerId != session.learner_id:
            raise ValidationError("The session learner does not match the lesson package learner")
        return package
