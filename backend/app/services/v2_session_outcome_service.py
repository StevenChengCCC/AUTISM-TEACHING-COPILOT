from __future__ import annotations

from hashlib import sha256
import json
from statistics import mean, median

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.v2_dto import (
    CompleteSessionRequest,
    GoalSpecificDataSheetSpec,
    LessonPackageDto,
    LessonSession,
    SessionBreakAndReturnAggregate,
    SessionCompletionTemplateDto,
    SessionGeneralizationAggregate,
    SessionLatencyAggregate,
    SessionMaterialsAggregate,
    SessionOpportunitiesAggregate,
    SessionOutcomeDto,
    SessionPromptingAggregate,
    SessionResponsesAggregate,
    utc_now,
)
from app.services.v2_repositories import V2Repositories, repositories


_PROMPT_ORDER = {
    "independent": 0,
    "gesture": 1,
    "visual": 2,
    "model": 3,
    "brief_verbal": 4,
    "other": 5,
}


def _distinct(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


class V2SessionOutcomeService:
    """Completes a teaching session from teacher-recorded observable trials."""

    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos

    def completion_template(self, session_id: str) -> SessionCompletionTemplateDto:
        session, package = self._session_package(session_id)
        if session.status == "draft":
            raise ConflictError("Start or plan the session before recording its outcome")
        snapshot = session.use_snapshot
        if snapshot is not None:
            return SessionCompletionTemplateDto(
                sessionId=session.id,
                learnerId=snapshot.learnerId,
                lessonPackageId=snapshot.packageId,
                lessonPackageRevision=snapshot.packageRevision,
                lessonSpecId=snapshot.lessonSpecId,
                goalId=snapshot.goalId,
                goalRevision=snapshot.goalRevision,
                operationalizedGoal=snapshot.operationalizedGoal,
                plannedOpportunities=snapshot.plannedOpportunities,
                contexts=snapshot.teacherConfirmedContexts,
                materialIds=list(snapshot.materialRevisions),
                materialLabels=snapshot.materialLabels,
                dataSheetColumns=snapshot.dataMeasures,
                sessionUseSnapshotId=snapshot.id,
            )
        spec = package.lessonSpec
        assert spec is not None
        planned = (
            spec.goal.success_criterion.total_opportunities
            if spec.goal.success_criterion and spec.goal.success_criterion.total_opportunities
            else max(1, len(spec.contexts))
        )
        columns: list[str] = []
        for material in package.materials:
            if isinstance(material.materialSpec, GoalSpecificDataSheetSpec):
                columns = list(material.materialSpec.content.exact_columns)
                break
            if getattr(material.specification, "type", None) == "data_sheet":
                columns = list(getattr(material.specification, "columns", []))
                break
        return SessionCompletionTemplateDto(
            sessionId=session.id,
            learnerId=session.learner_id,
            lessonPackageId=package.id,
            lessonPackageRevision=package.version,
            lessonSpecId=spec.id,
            goalId=self.goal_id(spec),
            goalRevision=spec.revision,
            operationalizedGoal=spec.goal.observable_behavior,
            plannedOpportunities=planned,
            contexts=spec.contexts,
            materialIds=[item.id for item in package.materials],
            materialLabels={item.id: item.title for item in package.materials},
            dataSheetColumns=columns,
        )

    def complete(
        self,
        session_id: str,
        request: CompleteSessionRequest,
        *,
        draft_completion_idempotency_key: str | None = None,
    ) -> SessionOutcomeDto:
        if self.for_session(session_id, required=False) is not None:
            raise ConflictError("This teaching session already has a completed outcome")
        session, package = self._session_package(session_id)
        spec = package.lessonSpec
        assert spec is not None
        snapshot = session.use_snapshot
        expected_package_id = snapshot.packageId if snapshot else package.id
        expected_package_revision = snapshot.packageRevision if snapshot else package.version
        expected_spec_id = snapshot.lessonSpecId if snapshot else spec.id
        expected_goal_id = snapshot.goalId if snapshot else self.goal_id(spec)
        expected_goal_revision = snapshot.goalRevision if snapshot else spec.revision
        operationalized_goal = snapshot.operationalizedGoal if snapshot else spec.goal.observable_behavior
        goal_comparison_key = snapshot.goalComparisonKey if snapshot else self.goal_comparison_key(spec)
        if request.expectedLessonPackageId != expected_package_id:
            raise ConflictError("The completion form belongs to a different lesson package")
        if request.expectedLessonSpecId != expected_spec_id:
            raise ConflictError("The session outcome LessonSpec does not match the session")
        if request.expectedGoalId != expected_goal_id:
            raise ConflictError("The session outcome goal does not match the session LessonSpec")

        template = self.completion_template(session_id)
        if len(request.trials) != template.plannedOpportunities:
            raise ValidationError(
                "Record every planned opportunity; mark opportunities that did not occur as cancelled"
            )
        initial_valid_trials = [item for item in request.trials if item.valid]
        if len(initial_valid_trials) > template.plannedOpportunities:
            raise ValidationError("Valid opportunities cannot exceed planned opportunities")

        allowed_contexts = {
            item.id: item for item in (
                snapshot.teacherConfirmedContexts if snapshot else spec.contexts
            )
        }
        package_material_ids = (
            set(snapshot.materialRevisions) if snapshot else {item.id for item in package.materials}
        )
        enriched_trials = []
        for trial in request.trials:
            context = allowed_contexts.get(trial.contextId)
            if context is None or context.label != trial.contextLabel:
                raise ValidationError(
                    f"Trial {trial.trialId} references a context outside the session LessonSpec"
                )
            unknown = set(trial.materialIdsUsed) - package_material_ids
            if unknown:
                raise ValidationError(
                    f"Trial {trial.trialId} references materials outside the session package: {', '.join(sorted(unknown))}"
                )
            enriched_trials.append(trial.model_copy(update={
                "contextDimension": context.generalization_dimension,
                "contextSetting": context.setting,
                "transitionFrom": context.transition_from,
                "transitionTo": context.transition_to,
            }))
        feedback_ids = set(request.helpfulMaterialIds) | set(request.unhelpfulMaterialIds)
        unknown_feedback = feedback_ids - package_material_ids
        if unknown_feedback:
            raise ValidationError(
                "Material feedback references materials outside the session package: "
                + ", ".join(sorted(unknown_feedback))
            )

        valid_trials = [item for item in enriched_trials if item.valid]
        used_material_ids = _distinct([
            material_id for trial in valid_trials for material_id in trial.materialIdsUsed
        ])
        successful = [
            item for item in valid_trials
            if item.outcome in {"independent_success", "prompted_success"}
        ]
        prompt_counts: dict[str, int] = {}
        for trial in valid_trials:
            if trial.promptLevel is not None:
                prompt_counts[trial.promptLevel] = prompt_counts.get(trial.promptLevel, 0) + 1
        prompt_levels = [item.promptLevel for item in valid_trials if item.promptLevel is not None]
        latency_values = [item.latencySeconds for item in valid_trials if item.latencySeconds is not None]
        attempted_contexts = _distinct([item.contextLabel for item in valid_trials])
        successful_contexts = _distinct([item.contextLabel for item in successful])
        derived_settings = [
            allowed_contexts[item.contextId].setting
            for item in valid_trials
            if allowed_contexts[item.contextId].setting
        ]

        outcome = SessionOutcomeDto(
            id=self.repos.next_id("outcome"),
            sessionId=session.id,
            learnerId=session.learner_id,
            lessonPackageId=expected_package_id,
            lessonPackageRevision=expected_package_revision,
            lessonSpecId=expected_spec_id,
            goalId=expected_goal_id,
            goalRevision=expected_goal_revision,
            operationalizedGoal=operationalized_goal,
            goalComparisonKey=goal_comparison_key,
            startedAt=request.startedAt,
            completedAt=request.completedAt,
            opportunities=SessionOpportunitiesAggregate(
                planned=template.plannedOpportunities,
                valid=len(valid_trials),
                cancelled=sum(1 for item in request.trials if item.outcome == "cancelled"),
            ),
            responses=SessionResponsesAggregate(
                independentSuccessful=sum(1 for item in valid_trials if item.outcome == "independent_success"),
                promptedSuccessful=sum(1 for item in valid_trials if item.outcome == "prompted_success"),
                incorrect=sum(1 for item in valid_trials if item.outcome == "incorrect"),
                noResponse=sum(1 for item in valid_trials if item.outcome == "no_response"),
                notObservedOrUnsuccessful=sum(
                    1 for item in valid_trials
                    if item.outcome == "not_observed_unsuccessful"
                ),
                speechSuccessful=sum(1 for item in successful if item.responseMode == "speech"),
                aacSuccessful=sum(1 for item in successful if item.responseMode == "AAC"),
                pointingSuccessful=sum(1 for item in successful if item.responseMode == "pointing"),
                otherSuccessful=sum(1 for item in successful if item.responseMode == "other"),
                breakOrStopHonored=sum(1 for item in valid_trials if item.outcome == "break_honored"),
            ),
            prompting=SessionPromptingAggregate(
                promptLevelCounts=prompt_counts,
                averagePromptLevel=(
                    round(mean(_PROMPT_ORDER[item] for item in prompt_levels), 2)
                    if prompt_levels else None
                ),
                lowestPromptLevel=(min(prompt_levels, key=_PROMPT_ORDER.get) if prompt_levels else None),
                highestPromptLevel=(max(prompt_levels, key=_PROMPT_ORDER.get) if prompt_levels else None),
            ),
            latency=SessionLatencyAggregate(
                recordedTrialCount=len(latency_values),
                averageSeconds=round(mean(latency_values), 2) if latency_values else None,
                medianSeconds=round(median(latency_values), 2) if latency_values else None,
            ),
            generalization=SessionGeneralizationAggregate(
                status=request.generalization.status,
                contextsAttempted=attempted_contexts,
                contextsSuccessful=successful_contexts,
                people=_distinct(request.generalization.people),
                settings=_distinct([*derived_settings, *request.generalization.settings]),
                materials=_distinct(request.generalization.materials),
            ),
            breakAndReturn=SessionBreakAndReturnAggregate(
                breakRequests=sum(1 for item in valid_trials if item.breakRequested),
                breaksDelivered=sum(1 for item in valid_trials if item.breakDelivered),
                returnedAfterBreak=sum(1 for item in valid_trials if item.returnedAfterBreak is True),
            ),
            materials=SessionMaterialsAggregate(
                usedMaterialIds=used_material_ids,
                unusedMaterialIds=sorted(package_material_ids - set(used_material_ids)),
                helpfulMaterialIds=_distinct(request.helpfulMaterialIds),
                unhelpfulMaterialIds=_distinct(request.unhelpfulMaterialIds),
            ),
            observations=request.observations,
            trials=enriched_trials,
            sessionUseSnapshotId=snapshot.id if snapshot else None,
            sessionUseSnapshot=snapshot,
        )
        completed_draft = session.run_draft
        if completed_draft is not None:
            completed_draft = completed_draft.model_copy(update={
                "status": "completed",
                "completionIdempotencyKey": draft_completion_idempotency_key,
                "lastSavedAt": utc_now(),
                "version": completed_draft.version + 1,
            })
        completed_session = session.model_copy(update={
            "status": "completed",
            "lesson_package_revision": expected_package_revision,
            "lesson_spec_id": expected_spec_id,
            "goal_id": expected_goal_id,
            "goal_revision": expected_goal_revision,
            "operationalized_goal": operationalized_goal,
            "started_at": request.startedAt,
            "completed_at": request.completedAt,
            "run_draft": completed_draft,
            "updated_at": utc_now(),
        })
        with self.repos.transaction():
            saved = self.repos.session_outcomes.save(outcome)
            self.repos.sessions.save(completed_session)
        return saved

    def for_session(self, session_id: str, *, required: bool = True) -> SessionOutcomeDto | None:
        outcome = next(
            (item for item in self.repos.session_outcomes.list() if item.sessionId == session_id),
            None,
        )
        if outcome is None and required:
            raise NotFoundError("Session outcome not found")
        return outcome

    def for_learner(self, learner_id: str) -> list[SessionOutcomeDto]:
        return [
            item for item in self.repos.session_outcomes.list()
            if item.learnerId == learner_id
        ]

    def _session_package(self, session_id: str) -> tuple[LessonSession, LessonPackageDto]:
        session = self.repos.sessions.get(session_id)
        if not isinstance(session, LessonSession):
            raise NotFoundError("Lesson session not found")
        if not session.lesson_package_id:
            raise ValidationError("The session must be linked to a lesson package before completion")
        package = self.repos.lesson_packages.get(session.lesson_package_id)
        if not isinstance(package, LessonPackageDto):
            raise NotFoundError("Session lesson package not found")
        if package.learnerId != session.learner_id:
            raise ValidationError("The session learner does not match the lesson package learner")
        if package.lessonSpec is None:
            raise ValidationError("The session lesson package does not contain a LessonSpec")
        return session, package

    @staticmethod
    def goal_id(lesson_spec) -> str:
        return f"goal-{V2SessionOutcomeService.goal_comparison_key(lesson_spec)[:24]}"

    @staticmethod
    def goal_comparison_key(lesson_spec) -> str:
        """Identify materially equivalent observable targets across spec revisions."""

        criterion = (
            lesson_spec.goal.success_criterion.model_dump(mode="json", by_alias=True)
            if lesson_spec.goal.success_criterion else None
        )
        payload = {
            "observableBehavior": " ".join(
                lesson_spec.goal.observable_behavior.casefold().split()
            ),
            "successCriterion": criterion,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
