from __future__ import annotations

from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.v2_dto import (
    LearnerCreate,
    LearnerProfile,
    LearnerProfileDto,
    LearnerUpdate,
)
from app.services.v2_repositories import V2Repositories, repositories


class V2LearnerService:
    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos

    def list(self) -> list[LearnerProfile]:
        return self.repos.learners.list()

    def list_dtos(self) -> list[LearnerProfileDto]:
        return [self.to_dto(learner) for learner in self.list()]

    def get(self, learner_id: str) -> LearnerProfile:
        learner = self.repos.learners.get(learner_id)
        if not learner:
            raise NotFoundError("Learner not found")
        return learner

    def get_dto(self, learner_id: str) -> LearnerProfileDto:
        return self.to_dto(self.get(learner_id))

    def create(self, payload: LearnerCreate) -> LearnerProfile:
        if any(item.code == payload.code for item in self.repos.learners.list()):
            raise ConflictError("Learner code already exists")
        learner = LearnerProfile(id=self.repos.next_id("learner"), **payload.model_dump())
        return self.repos.learners.save(learner)

    def create_dto(self, payload: LearnerCreate) -> LearnerProfileDto:
        return self.to_dto(self.create(payload))

    def update(self, learner_id: str, payload: LearnerUpdate) -> LearnerProfile:
        learner = self.get(learner_id)
        updated = learner.model_copy(update=payload.model_dump(exclude_none=True))
        return self.repos.learners.save(updated)

    def update_dto(
        self, learner_id: str, payload: LearnerUpdate
    ) -> LearnerProfileDto:
        return self.to_dto(self.update(learner_id, payload))

    @staticmethod
    def to_dto(learner: LearnerProfile) -> LearnerProfileDto:
        return LearnerProfileDto(
            id=learner.id,
            code=learner.code,
            age=learner.age,
            avatar=learner.avatar,
            tags=learner.tags,
            interests=learner.interests,
            supportNeeds=learner.support_needs,
            reinforcementPreferences=learner.reinforcement_preferences,
            communicationMode=learner.communication_mode,
            attentionProfile=learner.attention_profile,
            notes=learner.notes,
        )
