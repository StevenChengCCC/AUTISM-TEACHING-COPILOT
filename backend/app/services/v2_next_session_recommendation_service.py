from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.v2_dto import (
    NextSessionRecommendationDto,
    RecommendationEvidence,
    RecommendationReviewEvent,
    ReviewNextSessionRecommendationRequest,
    SessionOutcomeDto,
    utc_now,
)
from app.services.v2_goal_progress_service import V2GoalProgressService
from app.services.v2_repositories import V2Repositories, repositories


_PROHIBITED_LANGUAGE = (
    "diagnose", "diagnosis", "prescribe", "treatment intensity", "restrictive procedure",
    "restraint", "seclusion", "defiant", "defiance", "withhold a break",
    "remove breaks", "treatment is effective", "intervention is effective",
    "has mastered", "is regressing", "must comply",
)


class V2NextSessionRecommendationService:
    """Create review-only suggestions from deterministic structured evidence."""

    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos
        self.progress = V2GoalProgressService(repos)

    def list(
        self,
        learner_id: str,
        *,
        goal_id: str | None = None,
        goal_revision: int | None = None,
    ) -> list[NextSessionRecommendationDto]:
        values = [
            item for item in self.repos.next_session_recommendations.list()
            if item.learnerId == learner_id
            and (not goal_id or item.goalId == goal_id)
            and (goal_revision is None or item.goalRevision == goal_revision)
        ]
        return sorted(values, key=lambda item: (item.createdAt, item.id), reverse=True)

    def generate(
        self, learner_id: str, goal_id: str, goal_revision: int
    ) -> list[NextSessionRecommendationDto]:
        outcomes = self._comparable_outcomes(learner_id, goal_id, goal_revision)
        if not outcomes:
            raise ValidationError(
                "A completed session with observable evidence is required before recommendations can be generated"
            )
        proposals: list[NextSessionRecommendationDto] = []
        total_valid = sum(item.opportunities.valid for item in outcomes)
        if len(outcomes) < 3 or total_valid < 9:
            proposals.append(self._collect_more_data(outcomes))
        else:
            proposals.extend(self._stable_material_reuse(outcomes))
            proposals.extend(self._unhelpful_material_review(outcomes))
            context = self._lower_context_practice(outcomes)
            if context is not None:
                proposals.append(context)
            communication = self._preserve_communication_access(outcomes)
            if communication is not None:
                proposals.append(communication)
            fading = self._cautious_prompt_fading(outcomes)
            if fading is not None:
                proposals.append(fading)
        missing = self._missing_measurement_question(outcomes)
        if missing is not None:
            proposals.append(missing)

        existing = {
            item.id: item for item in self.list(
                learner_id, goal_id=goal_id, goal_revision=goal_revision
            )
        }
        saved = []
        with self.repos.transaction():
            for proposal in proposals:
                self._validate_safety(proposal)
                current = existing.get(proposal.id)
                saved.append(
                    current
                    if current is not None
                    else self.repos.next_session_recommendations.save(proposal)
                )
        return saved

    def review(
        self,
        recommendation_id: str,
        request: ReviewNextSessionRecommendationRequest,
    ) -> NextSessionRecommendationDto:
        current = self.repos.next_session_recommendations.get(recommendation_id)
        if current is None:
            raise NotFoundError("Next-session recommendation not found")
        if current.version != request.expectedVersion:
            raise ConflictError(
                "The recommendation changed after it was loaded. Refresh before reviewing it."
            )
        reviewed_at = utc_now()
        updated = current.model_copy(update={
            "status": request.action,
            "teacherEditedText": (
                request.teacherEditedText if request.action == "edited" else None
            ),
            "reviewedAt": reviewed_at,
            "reviewHistory": [
                *current.reviewHistory,
                RecommendationReviewEvent(
                    action=request.action,
                    teacherText=(
                        request.teacherEditedText if request.action == "edited" else None
                    ),
                    reviewedAt=reviewed_at,
                ),
            ],
        })
        saved = self.repos.next_session_recommendations.save(updated)
        self.repos.record_audit(
            "review_next_session_recommendation",
            "next_session_recommendation",
            recommendation_id,
            {
                "status": request.action,
                "goalId": current.goalId,
                "teacherEditPresent": request.teacherEditedText is not None,
            },
        )
        return saved

    def _comparable_outcomes(
        self, learner_id: str, goal_id: str, goal_revision: int
    ) -> list[SessionOutcomeDto]:
        candidates = sorted(
            [
                item for item in self.repos.session_outcomes.list()
                if item.learnerId == learner_id and item.goalId == goal_id
            ],
            key=lambda item: item.completedAt,
        )
        reference = next(
            (item for item in reversed(candidates) if item.goalRevision == goal_revision),
            None,
        )
        if reference is None:
            return []
        comparison = reference.goalComparisonKey or f"legacy-revision:{goal_revision}"
        return [
            item for item in candidates
            if (item.goalComparisonKey or f"legacy-revision:{item.goalRevision}") == comparison
        ]

    def _collect_more_data(
        self, outcomes: list[SessionOutcomeDto]
    ) -> NextSessionRecommendationDto:
        evidence = [self._rate_evidence(item) for item in outcomes]
        return self._proposal(
            outcomes,
            rule_id="insufficient-data-preserve-plan-v1",
            recommendation_type="collect_more_data",
            title="Preserve the current plan while collecting more observations",
            recommendation=(
                "More observations may be useful before changing the current lesson plan. "
                "The teacher may consider using the same observable goal and recording every valid opportunity in the next session."
            ),
            evidence=evidence,
            confidence="high",
            confidence_reason=(
                f"Only {len(outcomes)} completed session(s) and "
                f"{sum(item.opportunities.valid for item in outcomes)} valid opportunities are available."
            ),
            affected_lesson_paths=[],
        )

    def _stable_material_reuse(
        self, outcomes: list[SessionOutcomeDto]
    ) -> list[NextSessionRecommendationDto]:
        recent = outcomes[-3:]
        material_index = self._material_index(outcomes)
        unhelpful = {
            material_id for item in outcomes for material_id in item.materials.unhelpfulMaterialIds
        }
        candidates = []
        for material_id, (title, material_type) in material_index.items():
            if material_type not in {"break_card", "visual_timer"} or material_id in unhelpful:
                continue
            used_sessions = [
                item for item in recent if material_id in item.materials.usedMaterialIds
            ]
            if len(used_sessions) == len(recent):
                candidates.append((material_id, title, material_type, used_sessions))
        if not candidates:
            return []
        ids = [item[0] for item in candidates]
        titles = [item[1] for item in candidates]
        types = [item[2] for item in candidates]
        evidence = [
            RecommendationEvidence(
                sessionId=outcome.sessionId,
                description=(
                    f"{title} was recorded as used in this session; this describes use, not material effectiveness."
                ),
                metricPath="materials.usedMaterialIds",
                observedValue=True,
            )
            for _material_id, title, _material_type, sessions in candidates
            for outcome in sessions
        ]
        evidence.extend(
            RecommendationEvidence(
                sessionId=outcome.sessionId,
                description=(
                    f"This session recorded {outcome.breakAndReturn.breakRequests} break request(s), "
                    f"{outcome.breakAndReturn.breaksDelivered} delivered break(s), and "
                    f"{outcome.breakAndReturn.returnedAfterBreak} return(s) after a break."
                ),
                metricPath=(
                    "breakAndReturn.breakRequests,breakAndReturn.breaksDelivered,"
                    "breakAndReturn.returnedAfterBreak"
                ),
                observedValue=(
                    f"requested={outcome.breakAndReturn.breakRequests}; "
                    f"delivered={outcome.breakAndReturn.breaksDelivered}; "
                    f"returned={outcome.breakAndReturn.returnedAfterBreak}"
                ),
            )
            for outcome in recent
        )
        return [self._proposal(
            outcomes,
            rule_id="reuse-consistently-recorded-access-supports-v1",
            recommendation_type="reuse",
            title="Reuse consistently recorded communication and timing supports",
            recommendation=(
                f"The teacher may consider reusing {self._join(titles)} to keep communication access and break timing available while gathering the next observation."
            ),
            evidence=evidence,
            confidence="medium",
            confidence_reason=(
                "Each listed material was recorded as used in all three most recent sessions and was not rated unhelpful. Use does not establish causality."
            ),
            affected_material_ids=ids,
            affected_material_types=types,
        )]

    def _unhelpful_material_review(
        self, outcomes: list[SessionOutcomeDto]
    ) -> list[NextSessionRecommendationDto]:
        material_index = self._material_index(outcomes)
        evidence_by_material: dict[str, list[RecommendationEvidence]] = defaultdict(list)
        for outcome in outcomes:
            for material_id in outcome.materials.unhelpfulMaterialIds:
                title, _material_type = material_index.get(
                    material_id, (material_id, "unknown")
                )
                evidence_by_material[material_id].append(RecommendationEvidence(
                    sessionId=outcome.sessionId,
                    description=(
                        f"The teacher marked {title} as needing change before reuse in this session; "
                        "this records teacher judgment and does not establish material causality."
                    ),
                    metricPath="materials.unhelpfulMaterialIds",
                    observedValue=material_id,
                ))
                if outcome.observations.teacherNotes:
                    evidence_by_material[material_id].append(RecommendationEvidence(
                        sessionId=outcome.sessionId,
                        description=(
                            "A teacher-authored note from the same session is preserved verbatim for review; no conclusion was inferred from its free text."
                        ),
                        metricPath="observations.teacherNotes",
                        observedValue=outcome.observations.teacherNotes,
                    ))
        proposals = []
        for material_id, evidence in evidence_by_material.items():
            title, material_type = material_index.get(material_id, (material_id, "unknown"))
            rating_count = sum(
                item.metricPath == "materials.unhelpfulMaterialIds" for item in evidence
            )
            proposals.append(self._proposal(
                outcomes,
                rule_id=f"review-teacher-needs-change-material-v2:{material_id}",
                recommendation_type="modify_material",
                title=f"Review one teacher-rated material: {title}",
                recommendation=(
                    f"The teacher may consider reviewing {title} and editing only the part that did not fit the recorded session before choosing it again."
                ),
                evidence=evidence,
                confidence="high" if rating_count > 1 else "medium",
                confidence_reason=(
                    f"The recommendation is based on {rating_count} explicit teacher needs-change marking(s), not inferred material impact."
                ),
                affected_material_ids=[material_id],
                affected_material_types=[material_type],
            ))
        return proposals

    def _lower_context_practice(
        self, outcomes: list[SessionOutcomeDto]
    ) -> NextSessionRecommendationDto | None:
        latest = outcomes[-1]
        series = self.progress.series(
            latest.learnerId,
            goal_id=latest.goalId,
            goal_revision=latest.goalRevision,
        )
        eligible = [item for item in series.contextSummaries if item.filterEligible]
        if len(eligible) < 2:
            return None
        high = max(eligible, key=lambda item: item.independentSuccessRate)
        low = min(eligible, key=lambda item: item.independentSuccessRate)
        if high.independentSuccessRate - low.independentSuccessRate < 20:
            return None
        evidence = self._context_evidence(outcomes, low.contextKey)
        scenario_ids = [
            material_id
            for material_id, (_title, material_type) in self._material_index(outcomes).items()
            if material_type == "scenario_cards"
        ]
        return self._proposal(
            outcomes,
            rule_id=f"add-lower-context-opportunity-v1:{low.contextKey}",
            recommendation_type="add_generalization",
            title=f"Consider one additional opportunity in {low.contextLabel}",
            recommendation=(
                f"The teacher may consider adding one practice opportunity in {low.contextLabel} while keeping the response modes and break access unchanged."
            ),
            evidence=evidence,
            confidence="medium",
            confidence_reason=(
                f"Across {low.sessionCount} sessions, this context had {low.independentSuccessfulCount} independent responses in {low.validOpportunityCount} valid opportunities ({low.independentSuccessRate}%), compared with {high.independentSuccessRate}% in {high.contextLabel}. Context differences do not establish causality."
            ),
            affected_lesson_paths=["/contexts"],
            affected_material_ids=scenario_ids,
            affected_material_types=["scenario_cards"] if scenario_ids else [],
        )

    def _preserve_communication_access(
        self, outcomes: list[SessionOutcomeDto]
    ) -> NextSessionRecommendationDto | None:
        speech = sum(item.responses.speechSuccessful for item in outcomes)
        aac = sum(item.responses.aacSuccessful for item in outcomes)
        if not speech or not aac:
            return None
        evidence = [
            RecommendationEvidence(
                sessionId=item.sessionId,
                description=(
                    f"Successful responses included speech={item.responses.speechSuccessful} and AAC={item.responses.aacSuccessful}."
                ),
                metricPath="responses.speechSuccessful,responses.aacSuccessful",
                observedValue=f"speech={item.responses.speechSuccessful}; AAC={item.responses.aacSuccessful}",
            )
            for item in outcomes
            if item.responses.speechSuccessful or item.responses.aacSuccessful
        ]
        return self._proposal(
            outcomes,
            rule_id="preserve-confirmed-response-modes-v1",
            recommendation_type="reuse",
            title="Keep speech and AAC equally valid",
            recommendation=(
                "The teacher may consider keeping speech and AAC equally valid in the next session so communication access is not reduced."
            ),
            evidence=evidence,
            confidence="high",
            confidence_reason=(
                f"Across the recorded sessions, {speech} successful response(s) used speech and {aac} used AAC."
            ),
            affected_lesson_paths=["/communicationPlan/acceptedModes"],
        )

    def _cautious_prompt_fading(
        self, outcomes: list[SessionOutcomeDto]
    ) -> NextSessionRecommendationDto | None:
        if len(outcomes) < 3:
            return None
        recent = outcomes[-3:]
        rates = [self._rate(item.responses.independentSuccessful, item.opportunities.valid) for item in recent]
        intrusive = sum(
            trial.promptLevel in {"model", "brief_verbal", "other"}
            for item in recent[-2:] for trial in item.trials if trial.valid
        )
        if not (
            rates[0] <= rates[1] <= rates[2]
            and rates[-2] >= 60
            and rates[-1] >= 60
            and intrusive == 0
        ):
            return None
        return self._proposal(
            outcomes,
            rule_id="cautious-context-bound-prompt-fading-v1",
            recommendation_type="prompt_fading",
            title="Review cautious prompt fading in stable recent opportunities",
            recommendation=(
                "The teacher may consider testing one less-intrusive prompt only in opportunities that have remained stable, while restoring the current support immediately when needed."
            ),
            evidence=[self._rate_evidence(item) for item in recent],
            confidence="medium",
            confidence_reason=(
                f"The last three rates were {self._join([f'{value}%' for value in rates])}, and the last two sessions recorded no model, brief-verbal, or more-intensive prompts."
            ),
            affected_lesson_paths=["/promptingPlan/sequence", "/promptingPlan/fadeRule"],
        )

    def _missing_measurement_question(
        self, outcomes: list[SessionOutcomeDto]
    ) -> NextSessionRecommendationDto | None:
        valid = sum(item.opportunities.valid for item in outcomes)
        latency = sum(item.latency.recordedTrialCount for item in outcomes)
        if not valid or latency / valid >= 0.5:
            return None
        evidence = [
            RecommendationEvidence(
                sessionId=item.sessionId,
                description=(
                    f"Latency was recorded for {item.latency.recordedTrialCount} of {item.opportunities.valid} valid opportunities."
                ),
                metricPath="latency.recordedTrialCount/opportunities.valid",
                observedValue=self._rate(item.latency.recordedTrialCount, item.opportunities.valid),
            )
            for item in outcomes
        ]
        return self._proposal(
            outcomes,
            rule_id="confirm-latency-measurement-v1",
            recommendation_type="teacher_question",
            title="Confirm whether response latency should be recorded",
            recommendation=(
                "The teacher may consider confirming whether response latency is useful for this goal before adding it to the next data-collection plan."
            ),
            evidence=evidence,
            confidence="high",
            confidence_reason=(
                f"Latency was recorded for {latency} of {valid} valid opportunities, so the current latency evidence is incomplete."
            ),
            affected_lesson_paths=["/measurementPlan/latency"],
        )

    def _proposal(
        self,
        outcomes: list[SessionOutcomeDto],
        *,
        rule_id: str,
        recommendation_type: str,
        title: str,
        recommendation: str,
        evidence: list[RecommendationEvidence],
        confidence: str,
        confidence_reason: str,
        affected_lesson_paths: list[str] | None = None,
        affected_material_ids: list[str] | None = None,
        affected_material_types: list[str] | None = None,
    ) -> NextSessionRecommendationDto:
        latest = outcomes[-1]
        fingerprint_payload = [
            {
                "sessionId": item.sessionId,
                "metricPath": item.metricPath,
                "observedValue": item.observedValue,
                "contextId": item.contextId,
                "contextLabel": item.contextLabel,
            }
            for item in evidence
        ]
        fingerprint = sha256(json.dumps(
            fingerprint_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        identifier = sha256(
            f"{latest.learnerId}|{latest.goalId}|{rule_id}|{fingerprint}".encode("utf-8")
        ).hexdigest()
        return NextSessionRecommendationDto(
            id=f"recommendation-{identifier[:24]}",
            learnerId=latest.learnerId,
            goalId=latest.goalId,
            goalRevision=latest.goalRevision,
            type=recommendation_type,
            title=title,
            recommendation=recommendation,
            evidence=evidence,
            confidence=confidence,
            confidenceReason=confidence_reason,
            teacherReviewRequired=True,
            affectedLessonSpecPaths=affected_lesson_paths or [],
            affectedMaterialIds=affected_material_ids or [],
            affectedMaterialTypes=affected_material_types or [],
            status="pending",
            ruleId=rule_id,
            evidenceFingerprint=fingerprint,
        )

    def _context_evidence(
        self, outcomes: list[SessionOutcomeDto], context_key: str
    ) -> list[RecommendationEvidence]:
        evidence = []
        for outcome in outcomes:
            trials = [
                item for item in outcome.trials
                if item.valid and self.progress.context_key(item) == context_key
            ]
            if not trials:
                continue
            independent = sum(item.outcome == "independent_success" for item in trials)
            evidence.append(RecommendationEvidence(
                sessionId=outcome.sessionId,
                description=(
                    f"In {trials[0].contextLabel}, {independent} of {len(trials)} valid opportunities were independent."
                ),
                metricPath="trials[context].independent_success/opportunities.valid",
                observedValue=self._rate(independent, len(trials)),
                contextId=trials[0].contextId,
                contextLabel=trials[0].contextLabel,
            ))
        return evidence

    @staticmethod
    def _rate_evidence(outcome: SessionOutcomeDto) -> RecommendationEvidence:
        value = V2NextSessionRecommendationService._rate(
            outcome.responses.independentSuccessful, outcome.opportunities.valid
        )
        return RecommendationEvidence(
            sessionId=outcome.sessionId,
            description=(
                f"{outcome.responses.independentSuccessful} of {outcome.opportunities.valid} valid opportunities were independent ({value}%)."
            ),
            metricPath="responses.independentSuccessful/opportunities.valid",
            observedValue=value,
        )

    def _material_index(
        self, outcomes: list[SessionOutcomeDto]
    ) -> dict[str, tuple[str, str]]:
        values = {}
        for outcome in outcomes:
            package = self.repos.lesson_packages.get(outcome.lessonPackageId)
            if package is None:
                continue
            for material in package.materials:
                values[material.id] = (material.title, material.type)
        return values

    @staticmethod
    def _validate_safety(recommendation: NextSessionRecommendationDto) -> None:
        if not recommendation.teacherReviewRequired or recommendation.status != "pending":
            raise ValidationError("Generated recommendations must require pending teacher review")
        if not recommendation.evidence or any(
            not item.sessionId or not item.metricPath or item.observedValue is None
            for item in recommendation.evidence
        ):
            raise ValidationError(
                "Every recommendation requires session-linked evidence with an observable value"
            )
        protected_text = " ".join([
            recommendation.title,
            recommendation.recommendation,
            recommendation.confidenceReason,
            *[item.description for item in recommendation.evidence],
        ]).casefold()
        prohibited = [item for item in _PROHIBITED_LANGUAGE if item in protected_text]
        if prohibited:
            raise ValidationError(
                "Recommendation crossed a protected-language boundary: " + ", ".join(prohibited)
            )

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator * 100, 1) if denominator else 0.0

    @staticmethod
    def _join(values: list[str]) -> str:
        if len(values) <= 1:
            return values[0] if values else ""
        if len(values) == 2:
            return f"{values[0]} and {values[1]}"
        return f"{', '.join(values[:-1])}, and {values[-1]}"
