from __future__ import annotations

from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.v2_dto import (
    LearnerCreate,
    LearnerProfile,
    LearnerProfileDto,
    LearnerProfileVersionDto,
    LearnerUpdate,
    ProfileConfirmRequest,
    ProfileSignalReviewRequest,
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
        learner = LearnerProfile(
            id=self.repos.next_id("learner"), **payload.model_dump()
        )
        return self.repos.learners.save(learner)

    def create_dto(self, payload: LearnerCreate) -> LearnerProfileDto:
        return self.to_dto(self.create(payload))

    def update(self, learner_id: str, payload: LearnerUpdate) -> LearnerProfile:
        learner = self.get(learner_id)
        changes = payload.model_dump(exclude_none=True, exclude={"expected_version"})
        next_code = changes.get("code")
        if next_code and any(
            item.id != learner_id and item.code == next_code
            for item in self.repos.learners.list()
        ):
            raise ConflictError("Learner code already exists")
        if payload.expected_version is not None:
            learner = learner.model_copy(update={"version": payload.expected_version})
        updated = learner.model_copy(update=changes)
        return self.repos.learners.save(updated)

    def update_dto(self, learner_id: str, payload: LearnerUpdate) -> LearnerProfileDto:
        return self.to_dto(self.update(learner_id, payload))

    def save(self, learner: LearnerProfile) -> LearnerProfile:
        """Persist a fully merged profile through the learner service boundary."""

        self.get(learner.id)
        return self.repos.learners.save(learner)

    def review_signal(
        self,
        learner_id: str,
        signal_id: str,
        payload: ProfileSignalReviewRequest,
    ) -> LearnerProfileDto:
        learner = self.get(learner_id)
        if learner.version != payload.expectedVersion:
            from app.core.exceptions import VersionConflictError

            raise VersionConflictError(
                "The learner profile changed after it was loaded. Refresh and try again."
            )
        found = False
        reviewed = []
        for signal in learner.profile_signals:
            if signal.id != signal_id:
                reviewed.append(signal)
                continue
            found = True
            status = (
                "confirmed"
                if payload.decision in {"confirm", "edit"}
                else "rejected" if payload.decision == "reject" else "suggested"
            )
            state = {
                "confirm": "confirmed",
                "edit": "edited",
                "reject": "rejected",
                "leave_unknown": "unknown",
            }[payload.decision]
            edited_value = (payload.editedValue or "").strip()
            reviewed.append(
                signal.model_copy(
                    update={
                        "status": status,
                        "teacher_review_state": state,
                        **(
                            {
                                "label": edited_value,
                                "suggested_profile_value": edited_value,
                            }
                            if payload.decision == "edit" and edited_value
                            else {}
                        ),
                    }
                )
            )
        if not found:
            raise NotFoundError("Profile signal not found")
        saved = self.repos.learners.save(
            learner.model_copy(
                update={
                    "profile_signals": reviewed,
                    "profile_review_status": "reviewed",
                }
            )
        )
        return self.to_dto(saved)

    def confirm_profile(
        self, learner_id: str, payload: ProfileConfirmRequest
    ) -> LearnerProfileDto:
        learner = self.get(learner_id)
        if learner.version != payload.expectedVersion:
            from app.core.exceptions import VersionConflictError

            raise VersionConflictError(
                "The learner profile changed after it was loaded. Refresh and try again."
            )
        saved = self.repos.learners.save(
            learner.model_copy(update={"profile_review_status": "confirmed"})
        )
        return self.to_dto(saved)

    def list_profile_versions(self, learner_id: str) -> list[LearnerProfileVersionDto]:
        self.get(learner_id)
        return [
            LearnerProfileVersionDto(
                learnerId=learner_id,
                version=item.version,
                reviewStatus=item.profile_review_status,
                snapshot=self.to_dto(item),
            )
            for item in self.repos.learners.list_versions(learner_id)
        ]

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
            strengths=learner.strengths,
            sensoryPreferences=learner.sensory_preferences,
            knownChallenges=learner.known_challenges,
            promptingPreferences=learner.prompting_preferences,
            currentGoals=learner.current_goals,
            readingLevel=learner.reading_level,
            activityDurationPreference=learner.activity_duration_preference,
            responseOptions=learner.response_options,
            receptiveSupports=learner.receptive_supports,
            expressiveSupports=learner.expressive_supports,
            environmentalConsiderations=learner.environmental_considerations,
            effectiveSupports=learner.effective_supports,
            ineffectiveSupports=learner.ineffective_supports,
            independenceProfile=learner.independence_profile,
            masteredSkills=learner.mastered_skills,
            emergingSkills=learner.emerging_skills,
            generalizationProfile=learner.generalization_profile,
            breakPreferences=learner.break_preferences,
            classroomBarriers=learner.classroom_barriers,
            profileSignals=learner.profile_signals,
            unknownFields=learner.unknown_fields,
            profileReviewStatus=learner.profile_review_status,
            version=learner.version,
        )
