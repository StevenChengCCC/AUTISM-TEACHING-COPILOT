from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
from statistics import mean

from app.core.config import Settings, get_settings
from app.schemas.v2_dto import (
    GoalContextSummary,
    GoalMaterialUsageSummary,
    GoalProgressPoint,
    GoalProgressPointDetails,
    GoalProgressSeries,
    GoalProgressSeriesOption,
    ProgressMetric,
    SessionOutcomeDto,
    SessionTrialObservation,
)
from app.services.v2_repositories import V2Repositories, repositories


_PROMPT_DISPLAY_VALUES = {
    "independent": 100,
    "gesture": 75,
    "visual": 75,
    "model": 50,
    "brief_verbal": 25,
    "other": 0,
}
_PROMPT_LEVEL_VALUES = {
    "independent": 0,
    "gesture": 1,
    "visual": 2,
    "model": 3,
    "brief_verbal": 4,
    "other": 5,
}


def _prompt_value(trial: SessionTrialObservation, scale: dict[str, int]) -> int | None:
    level = trial.promptLevel
    if level is None and trial.outcome == "independent_success":
        level = "independent"
    return scale.get(level) if level is not None else None


class V2GoalProgressService:
    """Build transparent goal- and context-bound series from persisted trials."""

    def __init__(
        self,
        repos: V2Repositories = repositories,
        config: Settings | None = None,
    ):
        self.repos = repos
        self.config = config or get_settings()

    def series_options(self, learner_id: str) -> list[GoalProgressSeriesOption]:
        groups: dict[tuple[str, str], list[SessionOutcomeDto]] = defaultdict(list)
        for outcome in self._outcomes(learner_id):
            groups[(outcome.goalId, self._comparison_group(outcome))].append(outcome)
        options = []
        for outcomes in groups.values():
            ordered = sorted(outcomes, key=lambda item: item.completedAt)
            latest = ordered[-1]
            options.append(GoalProgressSeriesOption(
                goalId=latest.goalId,
                goalRevision=latest.goalRevision,
                operationalizedGoal=latest.operationalizedGoal,
                sessionCount=len(ordered),
                latestCompletedAt=latest.completedAt,
            ))
        return sorted(options, key=lambda item: item.latestCompletedAt, reverse=True)

    def series(
        self,
        learner_id: str,
        *,
        goal_id: str | None = None,
        goal_revision: int | None = None,
        metric: ProgressMetric = "independent_success_rate",
        context_key: str | None = None,
    ) -> GoalProgressSeries:
        outcomes = self._outcomes(learner_id)
        candidates = [item for item in outcomes if not goal_id or item.goalId == goal_id]
        reference = None
        if goal_revision is not None:
            reference = next(
                (item for item in reversed(candidates) if item.goalRevision == goal_revision),
                None,
            )
        if reference is None and candidates:
            reference = candidates[-1]
        if reference is None:
            return GoalProgressSeries(
                learnerId=learner_id,
                goalId=goal_id or "",
                goalRevision=goal_revision or 1,
                operationalizedGoal="",
                metric=metric,
                points=[],
                trend="no_data",
                trendEvidence=["No completed sessions are available for this goal."],
                latestValue=None,
                sessionCount=0,
                confidence="low",
                confidenceReasons=["No completed sessions are available."],
                activeContextKey=context_key,
            )

        group = self._comparison_group(reference)
        comparable = [
            item for item in candidates if self._comparison_group(item) == group
        ]
        comparable.sort(key=lambda item: item.completedAt)
        context_summaries = self._context_summaries(comparable)
        material_summaries = self._material_summaries(comparable)

        selected: list[tuple[SessionOutcomeDto, list[SessionTrialObservation]]] = []
        for outcome in comparable:
            valid_trials = [item for item in outcome.trials if item.valid]
            if context_key:
                valid_trials = [
                    item for item in valid_trials if self.context_key(item) == context_key
                ]
            if valid_trials:
                selected.append((outcome, valid_trials))

        points: list[GoalProgressPoint] = []
        previous_revision = None
        previous_spec_id = None
        for outcome, trials in selected:
            annotation = None
            if previous_revision is not None and (
                outcome.goalRevision != previous_revision
                or outcome.lessonSpecId != previous_spec_id
            ):
                annotation = (
                    f"Lesson specification changed from goal revision {previous_revision} "
                    f"to {outcome.goalRevision}; the observable behavior and success "
                    "criterion remained materially equivalent."
                )
            points.append(self._point(outcome, trials, metric, annotation))
            previous_revision = outcome.goalRevision
            previous_spec_id = outcome.lessonSpecId

        trend, evidence = self._trend(points, metric)
        confidence, confidence_reasons = self._series_confidence(selected, points)
        latest = comparable[-1]
        return GoalProgressSeries(
            learnerId=learner_id,
            goalId=latest.goalId,
            goalRevision=latest.goalRevision,
            operationalizedGoal=latest.operationalizedGoal,
            metric=metric,
            points=points,
            trend=trend,
            trendEvidence=evidence,
            latestValue=points[-1].value if points else None,
            sessionCount=len(points),
            confidence=confidence,
            confidenceReasons=confidence_reasons,
            activeContextKey=context_key,
            contextSummaries=context_summaries,
            materialUsageSummaries=material_summaries,
        )

    def _point(
        self,
        outcome: SessionOutcomeDto,
        trials: list[SessionTrialObservation],
        metric: ProgressMetric,
        annotation: str | None,
    ) -> GoalProgressPoint:
        valid = len(trials)
        independent = sum(item.outcome == "independent_success" for item in trials)
        prompted = sum(item.outcome == "prompted_success" for item in trials)
        numerator = independent
        confidence = "normal" if valid >= 3 else "low"
        confidence_reason = (
            None if confidence == "normal"
            else f"Only {valid} valid teaching opportunities were recorded; fewer than three is low confidence."
        )
        if metric == "independent_success_rate":
            value = self._rate(numerator, valid)
        elif metric == "prompt_independence_display_score":
            prompt_values = [
                prompt_score for item in trials
                if (prompt_score := _prompt_value(item, _PROMPT_DISPLAY_VALUES)) is not None
            ]
            numerator = len(prompt_values)
            value = round(mean(prompt_values), 1) if prompt_values else 0.0
        elif metric == "average_response_latency":
            latencies = [item.latencySeconds for item in trials if item.latencySeconds is not None]
            numerator = len(latencies)
            value = round(mean(latencies), 1) if latencies else 0.0
            if not latencies:
                confidence = "low"
                confidence_reason = "No valid trials included a recorded response latency."
        elif metric == "generalization_context_count":
            numerator = len({self.context_key(item) for item in trials})
            value = float(numerator)
        else:
            delivered = sum(item.breakDelivered for item in trials)
            numerator = sum(item.returnedAfterBreak is True for item in trials)
            value = self._rate(numerator, delivered)
            if delivered == 0:
                confidence = "low"
                confidence_reason = "No delivered breaks were available for a return-after-break rate."

        successful = [
            item for item in trials
            if item.outcome in {"independent_success", "prompted_success"}
        ]
        response_modes = {
            label: sum(item.responseMode == label for item in successful)
            for label in ("speech", "AAC", "pointing", "other")
        }
        prompt_counts = {
            label: sum(item.promptLevel == label for item in trials)
            for label in _PROMPT_LEVEL_VALUES
        }
        numeric_prompt_values = [
            prompt_score for item in trials
            if (prompt_score := _prompt_value(item, _PROMPT_LEVEL_VALUES)) is not None
        ]
        latencies = [item.latencySeconds for item in trials if item.latencySeconds is not None]
        material_ids = list(dict.fromkeys(
            material_id for item in trials for material_id in item.materialIdsUsed
        ))
        return GoalProgressPoint(
            sessionId=outcome.sessionId,
            completedAt=outcome.completedAt,
            goalId=outcome.goalId,
            goalRevision=outcome.goalRevision,
            metric=metric,
            value=value,
            validOpportunityCount=valid,
            numeratorCount=numerator,
            confidence=confidence,
            confidenceReason=confidence_reason,
            lessonPackageId=outcome.lessonPackageId,
            lessonPackageRevision=outcome.lessonPackageRevision,
            contextsAttempted=list(dict.fromkeys(item.contextLabel for item in trials)),
            annotation=annotation,
            details=GoalProgressPointDetails(
                operationalizedGoal=outcome.operationalizedGoal,
                independentSuccessfulCount=independent,
                promptedSuccessfulCount=prompted,
                responseModeCounts=response_modes,
                promptLevelCounts=prompt_counts,
                averagePromptLevel=(
                    round(mean(numeric_prompt_values), 2)
                    if numeric_prompt_values else None
                ),
                averageLatencySeconds=round(mean(latencies), 2) if latencies else None,
                breakRequestCount=sum(item.breakRequested for item in trials),
                breaksDeliveredCount=sum(item.breakDelivered for item in trials),
                returnedAfterBreakCount=sum(item.returnedAfterBreak is True for item in trials),
                materialIdsUsed=material_ids,
                teacherNotes=outcome.observations.teacherNotes,
            ),
        )

    def _context_summaries(
        self, outcomes: list[SessionOutcomeDto]
    ) -> list[GoalContextSummary]:
        groups: dict[str, list[tuple[SessionOutcomeDto, SessionTrialObservation]]] = defaultdict(list)
        for outcome in outcomes:
            for trial in outcome.trials:
                if trial.valid:
                    groups[self.context_key(trial)].append((outcome, trial))
        summaries = []
        for key, evidence in groups.items():
            first_trial = evidence[0][1]
            trials = [item[1] for item in evidence]
            session_ids = list(dict.fromkeys(item[0].sessionId for item in evidence))
            latencies = [item.latencySeconds for item in trials if item.latencySeconds is not None]
            reasons = []
            if len(session_ids) < self.config.PROGRESS_CONTEXT_MIN_FILTER_SESSIONS:
                reasons.append("Fewer than two sessions include this context.")
            if len(trials) < self.config.PROGRESS_CONTEXT_MIN_FILTER_OPPORTUNITIES:
                reasons.append("Fewer than three valid opportunities were recorded in this context.")
            latency_coverage = len(latencies) / len(trials)
            if latency_coverage < self.config.PROGRESS_CONTEXT_MIN_LATENCY_COVERAGE:
                reasons.append(
                    f"Response latency was recorded for only {len(latencies)} of {len(trials)} opportunities."
                )
            independent = sum(item.outcome == "independent_success" for item in trials)
            summaries.append(GoalContextSummary(
                contextKey=key,
                contextId=first_trial.contextId,
                contextLabel=first_trial.contextLabel,
                contextDimension=first_trial.contextDimension,
                contextSetting=first_trial.contextSetting,
                transitionFrom=first_trial.transitionFrom,
                transitionTo=first_trial.transitionTo,
                sessionCount=len(session_ids),
                validOpportunityCount=len(trials),
                independentSuccessfulCount=independent,
                promptedSuccessfulCount=sum(
                    item.outcome == "prompted_success" for item in trials
                ),
                independentSuccessRate=self._rate(independent, len(trials)),
                averagePromptLevel=(round(mean(prompt_values), 2) if (
                    prompt_values := [
                        prompt_score for item in trials
                        if (prompt_score := _prompt_value(item, _PROMPT_LEVEL_VALUES)) is not None
                    ]
                ) else None),
                averageLatencySeconds=round(mean(latencies), 2) if latencies else None,
                firstObservedAt=min(item[0].completedAt for item in evidence),
                lastObservedAt=max(item[0].completedAt for item in evidence),
                confidence="low" if reasons else "normal",
                confidenceReasons=reasons,
                evidenceSessionIds=session_ids,
                filterEligible=(
                    len(session_ids) >= self.config.PROGRESS_CONTEXT_MIN_FILTER_SESSIONS
                    and len(trials) >= self.config.PROGRESS_CONTEXT_MIN_FILTER_OPPORTUNITIES
                ),
            ))
        return sorted(
            summaries,
            key=lambda item: (-item.independentSuccessRate, item.contextLabel.casefold()),
        )

    def _material_summaries(
        self, outcomes: list[SessionOutcomeDto]
    ) -> list[GoalMaterialUsageSummary]:
        groups: dict[str, list[tuple[SessionOutcomeDto, SessionTrialObservation]]] = defaultdict(list)
        for outcome in outcomes:
            for trial in outcome.trials:
                if trial.valid:
                    for material_id in trial.materialIdsUsed:
                        groups[material_id].append((outcome, trial))
        summaries = []
        for material_id, evidence in groups.items():
            trials = [item[1] for item in evidence]
            by_context: dict[str, list[SessionTrialObservation]] = defaultdict(list)
            for trial in trials:
                by_context[trial.contextLabel].append(trial)
            summaries.append(GoalMaterialUsageSummary(
                materialId=material_id,
                materialLabel=self._material_label(material_id, evidence),
                sessionCount=len({item[0].sessionId for item in evidence}),
                validOpportunityCount=len(trials),
                independentSuccessfulCount=sum(
                    item.outcome == "independent_success" for item in trials
                ),
                promptedSuccessfulCount=sum(
                    item.outcome == "prompted_success" for item in trials
                ),
                unsuccessfulOpportunityCount=sum(
                    item.outcome in {"incorrect", "no_response"} for item in trials
                ),
                contextsWithIndependentResponses=sorted(
                    label for label, items in by_context.items()
                    if any(item.outcome == "independent_success" for item in items)
                ),
                contextsWithoutIndependentResponses=sorted(
                    label for label, items in by_context.items()
                    if not any(item.outcome == "independent_success" for item in items)
                ),
                evidenceSessionIds=list(dict.fromkeys(
                    item[0].sessionId for item in evidence
                )),
            ))
        return sorted(summaries, key=lambda item: (-item.sessionCount, item.materialLabel.casefold()))

    def _material_label(
        self,
        material_id: str,
        evidence: list[tuple[SessionOutcomeDto, SessionTrialObservation]],
    ) -> str:
        for outcome, _trial in reversed(evidence):
            package = self.repos.lesson_packages.get(outcome.lessonPackageId)
            if package is not None:
                material = next((item for item in package.materials if item.id == material_id), None)
                if material is not None:
                    return material.title
        return material_id

    def _series_confidence(
        self,
        selected: list[tuple[SessionOutcomeDto, list[SessionTrialObservation]]],
        points: list[GoalProgressPoint],
    ) -> tuple[str, list[str]]:
        reasons = []
        if len(points) < self.config.PROGRESS_TREND_MIN_NORMAL_POINTS:
            reasons.append(
                f"Fewer than {self.config.PROGRESS_TREND_MIN_NORMAL_POINTS} sessions are available for a stable pattern."
            )
        low_points = sum(item.confidence == "low" for item in points)
        if low_points:
            reasons.append(f"{low_points} session point(s) have low confidence.")
        context_sets = {
            frozenset(self.context_key(trial) for trial in trials)
            for _outcome, trials in selected
        }
        if len(context_sets) > 1:
            reasons.append("The mix of observed contexts changed between sessions.")
        trials = [trial for _outcome, items in selected for trial in items]
        latency_count = sum(item.latencySeconds is not None for item in trials)
        if trials and latency_count / len(trials) < self.config.PROGRESS_CONTEXT_MIN_LATENCY_COVERAGE:
            reasons.append(
                f"Response latency was recorded for only {latency_count} of {len(trials)} valid opportunities."
            )
        prompt_count = sum(
            item.promptLevel is not None or item.outcome == "independent_success"
            for item in trials
        )
        if prompt_count < len(trials):
            reasons.append(
                f"Prompt level was recorded for only {prompt_count} of {len(trials)} valid opportunities."
            )
        return ("low", reasons) if reasons else ("normal", [])

    def _trend(
        self, points: list[GoalProgressPoint], metric: ProgressMetric
    ) -> tuple[str, list[str]]:
        count = len(points)
        if count == 0:
            return "no_data", ["No completed sessions are available for this goal."]
        if count == 1:
            return "insufficient_data", [
                "One observation is available. More sessions are needed before identifying a stable pattern."
            ]
        if count == 2:
            return "comparison_only", [
                "Two observations are available. This shows a comparison but not a stable trend."
            ]
        normal = [item for item in points if item.confidence == "normal"]
        minimum = self.config.PROGRESS_TREND_MIN_NORMAL_POINTS
        if len(normal) < minimum:
            return "insufficient_data", [
                f"Only {len(normal)} of {count} observations have at least three valid opportunities. More observations are needed before identifying a stable pattern."
            ]
        recent = normal[-self.config.PROGRESS_TREND_LOOKBACK:]
        values = [item.value for item in recent]
        lower_is_better = metric == "average_response_latency"
        directed = [-value if lower_is_better else value for value in values]
        threshold = (
            self.config.PROGRESS_TREND_ABSOLUTE_THRESHOLD
            if metric in {"average_response_latency", "generalization_context_count"}
            else self.config.PROGRESS_TREND_PERCENTAGE_THRESHOLD
        )
        deltas = [right - left for left, right in zip(directed, directed[1:])]
        meaningful_up = sum(delta >= threshold for delta in deltas)
        meaningful_down = sum(delta <= -threshold for delta in deltas)
        rule = (
            f"The deterministic rule reviews up to {self.config.PROGRESS_TREND_LOOKBACK} "
            f"normal-confidence observations and requires at least two non-reversing changes of {threshold:g} or more; classification is based on repeated observations, not line slope alone."
        )
        if all(delta >= 0 for delta in deltas) and meaningful_up >= 2:
            language = (
                "Independent responses were higher in the most recent sessions."
                if metric == "independent_success_rate"
                else "The selected measure was more favorable in the most recent sessions."
            )
            return "improving", [language, rule, "This label does not establish mastery or causality."]
        if all(delta <= 0 for delta in deltas) and meaningful_down >= 2:
            language = (
                "Independent responses were lower in the most recent sessions."
                if metric == "independent_success_rate"
                else "The selected measure was less favorable in the most recent sessions."
            )
            return "declining", [language, rule, "This label does not establish regression or causality."]
        if max(values) - min(values) <= threshold:
            return "steady", [
                f"Recent values stayed within a {threshold:g}-unit range.",
                rule,
                "This label does not establish mastery.",
            ]
        return "variable", [
            f"Performance varied across the last {len(recent)} normal-confidence sessions.",
            rule,
        ]

    @staticmethod
    def context_key(trial: SessionTrialObservation) -> str:
        definition = {
            "id": trial.contextId.strip(),
            "label": trial.contextLabel.strip(),
            "dimension": trial.contextDimension,
            "setting": trial.contextSetting.strip(),
            "transitionFrom": trial.transitionFrom.strip(),
            "transitionTo": trial.transitionTo.strip(),
        }
        digest = sha256(
            json.dumps(definition, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"context-{digest[:24]}"

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator * 100, 1) if denominator else 0.0

    @staticmethod
    def _comparison_group(outcome: SessionOutcomeDto) -> str:
        return outcome.goalComparisonKey or f"legacy-revision:{outcome.goalRevision}"

    def _outcomes(self, learner_id: str) -> list[SessionOutcomeDto]:
        return sorted(
            [
                item for item in self.repos.session_outcomes.list()
                if item.learnerId == learner_id
            ],
            key=lambda item: item.completedAt,
        )
