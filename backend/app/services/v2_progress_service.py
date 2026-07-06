from statistics import mean, pstdev
from datetime import datetime, timezone

from app.core.exceptions import ValidationError
from app.schemas.v2_dto import (
    LearnerProgressSummaryDto,
    ProgressDataPointDto,
    ProgressObservation,
    ProgressSignalDto,
    ProgressSummary,
    SessionDataRecordRequest,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_repositories import V2Repositories, repositories


class V2ProgressService:
    """Tracks independence, prompting, engagement, regulation, and generalization—not accuracy alone."""

    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos
        self.learners = V2LearnerService(repos)

    def add_observation(self, observation: ProgressObservation) -> ProgressObservation:
        self.learners.get(observation.learner_id)
        return self.repos.progress.add(observation)

    def summarize(self, learner_id: str) -> ProgressSummary:
        self.learners.get(learner_id)
        items = self.repos.progress.for_learner(learner_id)
        if not items:
            return ProgressSummary(learner_id=learner_id, observation_count=0, trend="insufficient_data", strengths=[], support_priorities=["Collect observations across several sessions"])
        composite = [(item.independence_level + item.engagement_level + item.regulation_level + (4 - item.prompt_level)) / 4 for item in items]
        if len(items) < 3:
            trend = "insufficient_data"
        elif pstdev(composite) > 0.8:
            trend = "variable"
        elif mean(composite[-2:]) > mean(composite[:2]) + 0.4:
            trend = "emerging"
        else:
            trend = "steady"
        latest = items[-1]
        strengths = []
        if latest.engagement_level >= 3:
            strengths.append("Engagement is a current strength")
        if latest.generalization_contexts:
            strengths.append("Skill observed across contexts")
        priorities = []
        if latest.prompt_level >= 3:
            priorities.append("Continue gradual prompt fading")
        if latest.regulation_level <= 1:
            priorities.append("Prioritize regulation and pacing supports")
        return ProgressSummary(learner_id=learner_id, observation_count=len(items), trend=trend, strengths=strengths, support_priorities=priorities, latest_observation=latest)

    def product_summary(self, learner_id: str) -> LearnerProgressSummaryDto:
        self.learners.get(learner_id)
        summary = self.repos.progress_summaries.get(learner_id)
        if not summary:
            return LearnerProgressSummaryDto(
                learnerId=learner_id,
                currentGoal="No active goal",
                accuracyPercent=0,
                independencePercent=0,
                sessionsPracticed=0,
                currentPromptLevel="Not recorded",
                trend="Not enough data yet",
                message="Plateau does not mean no progress.",
            )
        return summary

    def product_signals(self, learner_id: str) -> list[ProgressSignalDto]:
        self.learners.get(learner_id)
        supported_types = {
            "engagement",
            "prompt_fading",
            "generalization",
            "regulation_recovery",
            "participation",
        }
        return [
            signal
            for signal in self.repos.progress_signals.list()
            if signal.type in supported_types
        ]

    def product_data(self, learner_id: str) -> list[ProgressDataPointDto]:
        self.learners.get(learner_id)
        return [
            point
            for point in self.repos.progress_data.list()
            if point.learnerId == learner_id
        ]

    def record_session_data(
        self, payload: SessionDataRecordRequest
    ) -> LearnerProgressSummaryDto:
        self.learners.get(payload.learnerId)
        if payload.opportunities <= 0:
            raise ValidationError("Opportunities must be greater than zero")
        if not 0 <= payload.correct <= payload.opportunities:
            raise ValidationError("Correct responses must be within opportunities")
        if not 0 <= payload.independent <= payload.opportunities:
            raise ValidationError("Independent responses must be within opportunities")

        point = ProgressDataPointDto(
            id=self.repos.next_id("progress"),
            learnerId=payload.learnerId,
            sessionDate=datetime.now(timezone.utc).date().isoformat(),
            goal=payload.goal,
            opportunities=payload.opportunities,
            accuracyPercent=round(payload.correct / payload.opportunities * 100),
            independencePercent=round(payload.independent / payload.opportunities * 100),
            promptLevel=payload.promptLevel,
            signalsHighlighted=payload.signalsHighlighted,
            teacherNotes=payload.teacherNotes,
        )
        self.repos.progress_data.save(point)
        points = self.product_data(payload.learnerId)
        first, latest = points[0], points[-1]
        independence_change = latest.independencePercent - first.independencePercent
        trend = (
            "Slow, uneven growth with emerging independence"
            if independence_change > 0
            else "Variable progress; continue observing small changes"
        )
        summary = LearnerProgressSummaryDto(
            learnerId=payload.learnerId,
            currentGoal=payload.goal,
            accuracyPercent=latest.accuracyPercent,
            independencePercent=latest.independencePercent,
            sessionsPracticed=len(points),
            currentPromptLevel=latest.promptLevel,
            trend=trend,
            message="Plateau does not mean no progress.",
        )
        return self.repos.progress_summaries.save(summary)
