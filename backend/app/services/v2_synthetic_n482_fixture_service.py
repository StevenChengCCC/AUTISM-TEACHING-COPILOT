from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings, settings
from app.core.exceptions import NotFoundError
from app.schemas.v2_dto import (
    CanonicalLearnerProfile,
    GenerationArtifactState,
    GenerationJobDto,
    GenerationStageState,
    GoalDecisionValue,
    LearnerProfile,
    LearnerProfileSummary,
    LessonDesignDraftDto,
    LessonPackageDecisionRequest,
    LessonSession,
    MaterialRequestDecisionValue,
    MaterialRequestItem,
    PracticeContextDecisionValue,
    PracticeContextItem,
    ProfileFactor,
    TeacherDecision,
)
from app.services.v2_instructional_constraint_service import (
    build_instructional_constraint_snapshot,
)
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_session_outcome_service import V2SessionOutcomeService


class V2SyntheticN482FixtureService:
    """Resettable browser fixture that is callable only in local development."""

    learner_id = "synthetic-n482"
    session_id = "synthetic-n482-session-planned"

    def __init__(
        self,
        repos: V2Repositories = repositories,
        config: Settings = settings,
    ) -> None:
        self.repos = repos
        self.config = config

    def reset(self) -> dict[str, Any]:
        if self.config.APP_ENV != "development":
            raise NotFoundError("Synthetic fixture not found")
        self._remove_existing()
        learner = self._learner()
        self.repos.learners.save(learner)
        snapshot = build_instructional_constraint_snapshot(learner, [])
        package_service = V2LessonPackageService(self.repos)
        draft = self._draft(snapshot)
        draft = draft.model_copy(
            update={"packageContentPlan": package_service.preview_content_plan(draft)}
        )

        original_next_id = self.repos.next_id
        counts: dict[str, int] = {}

        def stable_next_id(prefix: str) -> str:
            counts[prefix] = counts.get(prefix, 0) + 1
            return f"synthetic-n482-{prefix}-{counts[prefix]}"

        self.repos.next_id = stable_next_id  # type: ignore[method-assign]
        try:
            package = package_service.generate_product(draft)
        finally:
            self.repos.next_id = original_next_id  # type: ignore[method-assign]

        materials = V2MaterialService(self.repos)
        for material in package.materials:
            materials.review_generated(material.id)
            materials.approve_generated(material.id)
        current = package_service.get_product(package.id)
        approved = package_service.approve_product(
            current.id,
            LessonPackageDecisionRequest(
                expectedVersion=current.version,
                reason="Reset approved synthetic N-482 browser fixture",
            ),
        )
        spec = approved.lessonSpec
        completed_at = datetime.now(timezone.utc).isoformat()
        self.repos.generation_jobs.save(
            GenerationJobDto(
                jobId="synthetic-n482-generation-job-1",
                learnerId=learner.id,
                draftId=draft.id,
                lessonSpecId=spec.id if spec else "synthetic-n482-lesson-spec-1",
                lessonSpecRevision=spec.revision if spec else 1,
                packageContentPlanRevision=spec.revision if spec else 1,
                packageId=approved.id,
                requestedArtifactIds=[item.id for item in approved.materials],
                artifacts=[
                    GenerationArtifactState(
                        artifactId=item.id,
                        materialType=item.type,
                        status="completed",
                    )
                    for item in approved.materials
                ],
                stages=[
                    GenerationStageState(
                        stage=stage,
                        status="completed",
                        completedAt=completed_at,
                        updatedAt=completed_at,
                        message="Synthetic fixture stage is complete.",
                    )
                    for stage in (
                        "planning",
                        "material_specification",
                        "semantic_validation",
                        "repair",
                        "visual_planning",
                        "image_generation",
                        "rendering",
                        "safety_validation",
                        "pdf_composition",
                        "artifact_upload",
                        "download_readiness",
                    )
                ],
                status="completed",
                provider="deterministic-local",
                model="synthetic-fixture-v1",
                startedAt=completed_at,
                lastUpdatedAt=completed_at,
                completedAt=completed_at,
                idempotencyKey="synthetic-n482-generation-v1",
            )
        )
        session = self.repos.sessions.save(
            LessonSession(
                id=self.session_id,
                learner_id=learner.id,
                goal=approved.goal,
                status="planned",
                lesson_package_id=approved.id,
                lesson_package_revision=approved.version,
                lesson_spec_id=spec.id if spec else None,
                goal_id=(V2SessionOutcomeService.goal_id(spec) if spec else None),
                goal_revision=spec.revision if spec else None,
                operationalized_goal=(spec.goal.display_text if spec else approved.goal),
            )
        )
        return {
            "fixtureId": "synthetic-n482-break-request-v1",
            "label": "Synthetic N-482 break-request acceptance fixture",
            "synthetic": True,
            "learnerId": learner.id,
            "packageId": approved.id,
            "packageRevision": approved.version,
            "lessonSpecRevision": spec.revision if spec else 1,
            "sessionId": session.id,
            "resetAt": datetime.now(timezone.utc).isoformat(),
        }

    def _remove_existing(self) -> None:
        package_ids = {
            item.id
            for item in self.repos.lesson_packages.list()
            if getattr(item, "learnerId", None) == self.learner_id
        }

        def delete_where(repository: Any, predicate: Callable[[Any], bool]) -> None:
            for item in repository.list():
                if not predicate(item):
                    continue
                key = next(
                    (
                        getattr(item, name)
                        for name in ("id", "exportId", "jobId")
                        if getattr(item, name, None)
                    ),
                    None,
                )
                if key:
                    repository.delete(key)

        delete_where(
            self.repos.sessions,
            lambda item: getattr(item, "learner_id", None) == self.learner_id,
        )
        delete_where(
            self.repos.export_jobs,
            lambda item: getattr(item, "packageId", None) in package_ids,
        )
        delete_where(
            self.repos.generation_jobs,
            lambda item: getattr(item, "packageId", None) in package_ids,
        )
        delete_where(
            self.repos.materials_library,
            lambda item: (getattr(item, "configuration", {}) or {}).get("packageId")
            in package_ids,
        )
        delete_where(
            self.repos.generated_materials,
            lambda item: getattr(item, "packageId", None) in package_ids,
        )
        delete_where(
            self.repos.lesson_packages,
            lambda item: getattr(item, "learnerId", None) == self.learner_id,
        )
        delete_where(
            self.repos.records,
            lambda item: getattr(item, "learner_id", None) == self.learner_id,
        )
        self.repos.learners.delete(self.learner_id)

    @staticmethod
    def _factor(
        factor_id: str,
        category: str,
        value: str,
        *,
        status: str = "confirmed_current",
        constraint: str = "",
    ) -> ProfileFactor:
        return ProfileFactor(
            id=factor_id,
            category=category,
            label=factor_id.replace("-", " ").title(),
            value=value,
            status=status,
            confidence=1,
            sourceEvidence="Synthetic fixture evidence.",
            sourceRecordId=None,
            instructionalImplication=value,
            generationConstraints=[constraint] if constraint else [],
            teacherReviewed=True,
        )

    @classmethod
    def _learner(cls) -> LearnerProfile:
        f = cls._factor
        factors = [
            f("communication", "communication", "Speech and AAC are accepted equally"),
            f("wait-five", "prompting", "Wait at least five seconds", constraint="minimum_processing_wait_seconds=5"),
            f("prompt-sequence", "prompting", "Independent opportunity, visual or gestural cue, model, then brief verbal prompt"),
            f("no-hoh", "prohibited_item", "Hand-over-hand prompting is prohibited"),
            f("six-minute", "attention", "Maximum six-minute teaching block", constraint="maximum_teaching_block_minutes=6"),
            f("five-bus", "reinforcement", "Use a five-token board with bus-icon tokens", constraint="token_count=5"),
            f("reward", "reinforcement", "Two-minute transit-map reward"),
            f("praise", "reinforcement", "Specific praise: You asked for a break by yourself."),
            f("blue-lines", "current_interest", "Blue transit lines"),
            f("transition", "transition", "Use First-Then, a one-minute visual warning, and present First-Then again on return"),
            f("break", "regulation", "Honor a two-minute break request with a visible timer", constraint="break_duration_minutes=2"),
            f("low-clutter", "visual_access", "Use high-contrast low-clutter pages"),
            f("four-choices", "visual_access", "Use no more than four choices", constraint="maximum_response_options_per_page=4"),
            f("no-audio", "sensory", "No audio prompts, sound effects, applause, or alarms"),
            f("no-writing", "motor_access", "Do not require handwriting"),
            f("no-cutting", "motor_access", "Avoid fine-motor cutting"),
            f("generalization", "generalization", "Practice across transit-map activity to table work, art activity to cleanup, and free choice to shared reading", constraint="minimum_generalization_contexts=3"),
            f("spanish", "unresolved_assumption", "Whether paired Spanish labels improve comprehension", status="unconfirmed"),
            f("illustration", "unresolved_assumption", "Whether photographs or line drawings are preferred", status="unconfirmed"),
            f("food", "reinforcement", "Food rewards", status="not_approved"),
        ]
        profile = CanonicalLearnerProfile(
            learnerId=cls.learner_id,
            age=9,
            factors=factors,
            confirmedFactorIds=[
                item.id for item in factors if item.status == "confirmed_current"
            ],
            unconfirmedFactorIds=["spanish", "illustration"],
            excludedFactorIds=["food"],
            summary=LearnerProfileSummary(
                communication="Speech and AAC",
                supports=["First-Then"],
                currentInterests=["Blue transit lines"],
                learningFormat="Brief visual blocks",
                keyTeachingNotes=["Wait five seconds"],
            ),
        )
        return LearnerProfile(
            id=cls.learner_id,
            code="Synthetic N-482",
            age=9,
            avatar="",
            tags=["Synthetic fixture", "Break request", "Browser acceptance"],
            interests=["Blue transit lines"],
            support_needs=["Speech and AAC", "Five-second wait time", "Visual supports"],
            reinforcement_preferences=["Two-minute transit-map break", "Five bus tokens"],
            communication_mode="Speech and AAC",
            attention_profile="Six-minute teaching blocks with honored breaks",
            notes="Fully synthetic development fixture. No real learner data.",
            current_goals=["Requesting a break during transitions"],
            normalizedProfile=profile,
            profile_review_status="confirmed",
        )

    @classmethod
    def _draft(cls, snapshot: Any) -> LessonDesignDraftDto:
        goal = TeacherDecision(
            id="decision-goal",
            field="goal",
            source="teacher_edited",
            value=GoalDecisionValue(
                teacherRequest='Teach requesting "Break, please" during transitions.',
                interpretedGoal='Independently request "Break, please" using speech or AAC during transitions.',
                observableBehavior='Requests "Break, please" using speech or AAC',
                conditions="During selected transitions",
                acceptedResponseModes=["speech", "AAC"],
            ),
        )
        labels = [
            "transit-map activity to table work",
            "art activity to cleanup",
            "free choice to shared reading",
        ]
        contexts = [
            PracticeContextItem(
                id=f"context-{index}",
                label=label,
                setting=label,
                transitionFrom=label.split(" to ")[0],
                transitionTo=label.split(" to ")[1],
                generalizationDimension="activity",
            )
            for index, label in enumerate(labels, 1)
        ]
        context_decision = TeacherDecision(
            id="decision-contexts",
            field="practice_contexts",
            source="teacher_selected",
            optionIds=[item.id for item in contexts],
            value=PracticeContextDecisionValue(contexts=contexts),
        )
        requested = [
            ("blue_line_activity", "personalized Blue Line activity", "Practice the goal in a motivating transition context"),
            ("break_card", "Break, Please communication card", "Provide speech and AAC-equivalent communication access"),
            ("first_then_board", "concrete First-Then board", "Preview and support transition completion"),
            ("token_board", "five-bus-token board", "Represent progress toward the confirmed reward"),
            ("visual_timer", "two-minute visual timer", "Show the honored break duration without audio"),
            ("scenario_cards", "transition scenario cards", "Practice across three selected contexts"),
            ("data_sheet", "goal-specific data sheet", "Measure independent break requests and prompting"),
            ("summary_template", "lesson summary", "Document response modes and next steps"),
        ]
        materials = [
            MaterialRequestItem(
                requestId=f"request-{index}",
                materialType=material_type,
                customLabel=label,
                purpose=purpose,
                profileFactorIds=snapshot.profile_factor_ids,
                libraryConfiguration=(
                    {"activityTitle": "Complete the Blue Line"}
                    if material_type == "blue_line_activity"
                    else {
                        "firstTask": "Complete 3 table-work items",
                        "thenOutcome": "2-minute transit-map break",
                        "completionCriterion": "Complete all 3 table-work items",
                        "returnSupport": "After the break, check First-Then and return to the next table-work item.",
                    }
                    if material_type == "first_then_board"
                    else {"returnCue": "Break finished - check First-Then"}
                    if material_type == "visual_timer"
                    else None
                ),
            )
            for index, (material_type, label, purpose) in enumerate(requested, 1)
        ]
        material_decision = TeacherDecision(
            id="decision-materials",
            field="material_requests",
            source="teacher_selected",
            optionIds=[item.request_id for item in materials],
            value=MaterialRequestDecisionValue(materials=materials),
        )
        return LessonDesignDraftDto(
            id="synthetic-n482-draft",
            learnerId=cls.learner_id,
            goalText=goal.value.interpreted_goal,
            observableResponse=goal.value.observable_behavior,
            responseLevel="speech or AAC",
            scenarios=labels,
            selectedMaterials=[item.custom_label for item in materials],
            theme="Blue transit lines",
            duration="25 min",
            customNotes="",
            opportunities=5,
            profileRevision=snapshot.profile_revision,
            instructionalConstraintSnapshot=snapshot,
            teacherRequest=goal.value.teacher_request,
            decisions=[goal, context_decision, material_decision],
        )
