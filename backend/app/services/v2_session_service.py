from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.schemas.v2_dto import (
    LessonPackageDto,
    LessonSession,
    LessonSessionDto,
    LessonSessionStatDto,
    LessonSessionSummaryDto,
    RecentLessonDto,
    SessionCreate,
    utc_now,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_repositories import V2Repositories, repositories


class V2SessionService:
    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos
        self.learners = V2LearnerService(repos)

    def list(self) -> list[LessonSession]:
        sessions = self.repos.sessions.list()
        if not getattr(self.repos, "is_durable", False):
            return sessions
        known = {(item.learner_id, item.goal) for item in sessions}
        for package in self.repos.lesson_packages.list():
            if not isinstance(package, LessonPackageDto):
                continue
            key = (package.learnerId, package.goal)
            if key in known:
                continue
            recovered = LessonSession(
                id=f"session-{package.id}",
                learner_id=package.learnerId,
                goal=package.goal,
                status="planned",
            )
            sessions.append(self.repos.sessions.save(recovered))
            known.add(key)
        return sessions

    def list_dtos(self) -> list[LessonSessionDto]:
        return [self.to_dto(session) for session in self.list()]

    def stats(self) -> list[LessonSessionStatDto]:
        counts = {status: 0 for status in ("planned", "in_progress", "completed", "draft")}
        for session in self.list():
            counts[session.status] += 1
        definitions = [
            ("planned", "Planned", "Upcoming sessions"),
            ("in_progress", "In Progress", "Active sessions"),
            ("completed", "Completed", "Finished sessions"),
            ("draft", "Drafts", "Not yet scheduled"),
        ]
        return [
            LessonSessionStatDto(status=status, label=label, count=counts[status], helperText=helper)
            for status, label, helper in definitions
        ]

    def create(self, payload: SessionCreate) -> LessonSession:
        self.learners.get(payload.learner_id)
        session = LessonSession(id=self.repos.next_id("session"), **payload.model_dump())
        return self.repos.sessions.save(session)

    def create_dto(self, payload: SessionCreate) -> LessonSessionDto:
        return self.to_dto(self.create(payload))

    def duplicate(self, session_id: str) -> LessonSession:
        source = self.repos.sessions.get(session_id)
        if not source:
            raise NotFoundError("Session not found")
        duplicate = source.model_copy(update={"id": self.repos.next_id("session"), "status": "draft", "updated_at": utc_now()})
        return self.repos.sessions.save(duplicate)

    def duplicate_dto(self, session_id: str) -> LessonSessionDto:
        return self.to_dto(self.duplicate(session_id))

    def summary(self, session_id: str) -> LessonSessionSummaryDto:
        session = self.repos.sessions.get(session_id)
        if not session:
            raise NotFoundError("Lesson session not found")
        return LessonSessionSummaryDto(
            **self.to_dto(session).model_dump(),
            overview="Progress is interpreted across independence, prompting, participation, engagement, and regulation—not accuracy alone.",
            highlights=[
                "Small wins matter, including attempts made with less prompting.",
                "Participation and recovery can improve even when accuracy is uneven.",
            ],
            nextSteps=[
                "Continue gradual prompt fading.",
                "Offer another generalization opportunity in a familiar routine.",
            ],
        )

    def recent_lessons(self, learner_id: str) -> list[RecentLessonDto]:
        self.learners.get(learner_id)
        return [
            lesson
            for lesson in self.repos.recent_lessons.list()
            if lesson.learnerId == learner_id
        ]

    @staticmethod
    def to_dto(session: LessonSession) -> LessonSessionDto:
        return LessonSessionDto(
            id=session.id,
            learnerId=session.learner_id,
            goal=session.goal,
            status=session.status,
            updatedAt=session.updated_at.isoformat(),
        )
