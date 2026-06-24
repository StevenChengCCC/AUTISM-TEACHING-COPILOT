import json
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, SafetyDeferralError, ValidationError
from app.core.safety import classify_goal_safety
from app.repositories.audit import AuditLogRepository
from app.repositories.children import ChildProfileRepository
from app.repositories.goals import TeachingGoalRepository
from app.repositories.images import ImageAssetRepository, asset_to_candidate
from app.repositories.lessons import LessonPackageRepository, SessionRecordRepository
from app.domain.engines import (
    build_attention_segments,
    build_generalization_plan,
    build_reinforcement_plan,
    evaluate_progress,
)
from app.schemas.dto import (
    LessonPlanRequest,
    LessonPlanResponse,
    SessionRecordCreate,
    SessionRecordRead,
)
from app.services.profile_mapper import child_to_dict
from app.services.profile_completeness_service import ProfileCompletenessService
from app.services.printable_card_service import PrintableCardService


class LessonService:
    """Lesson generation service.

    Most logic is deterministic code to reduce token cost. AI is intentionally not required for MVP.
    """

    def __init__(self, db: Session):
        self.db = db
        self.children = ChildProfileRepository(db)
        self.goals = TeachingGoalRepository(db)
        self.images = ImageAssetRepository(db)
        self.lessons = LessonPackageRepository(db)
        self.records = SessionRecordRepository(db)

    def create_lesson(
        self, req: LessonPlanRequest, actor_teacher_id: int | None = None
    ) -> LessonPlanResponse:
        child = self.children.get(req.child_id)
        if not child:
            raise NotFoundError("Child profile not found")
        completeness = ProfileCompletenessService().check(child)
        if not completeness.is_complete:
            raise ValidationError(
                "Child profile is incomplete. Answer guided questions before generating a teaching package.",
                payload={"profile_completeness": completeness.model_dump()},
            )
        goal = self.goals.get(req.goal_id) if req.goal_id is not None else None
        if req.goal_id is not None and not goal:
            raise NotFoundError("Teaching goal not found")
        if goal and goal.child_id != req.child_id:
            raise NotFoundError("Teaching goal does not belong to child profile")

        target_skill = goal.target_skill if goal else req.target_skill
        concept = (
            goal.concept if goal and goal.concept else self._infer_concept(target_skill)
        )
        verdict = classify_goal_safety(
            target_skill=target_skill,
            concept=concept,
            notes=goal.notes if goal else None,
            behavior_notes=child.behavior_notes,
        )
        if verdict.requires_bcba:
            payload = {
                "requires_bcba": True,
                "category": verdict.category,
                "matched_terms": verdict.matched_terms,
                "message": "This goal targets behavior reduction and must be planned by a BCBA.",
            }
            AuditLogRepository(self.db).write(
                actor_teacher_id,
                "safety_deferral",
                "TeachingGoal",
                goal.id if goal else None,
                req.child_id,
                {
                    "category": verdict.category,
                    "matched_terms": verdict.matched_terms,
                },
            )
            raise SafetyDeferralError(payload)

        if not req.selected_image_asset_ids:
            raise ValidationError(
                "Teacher-confirmed images are required before saving a teaching package.",
                payload={
                    "guided_action": "Run the image pipeline, select candidate images, confirm them, then generate the package."
                },
            )
        selected_assets = self.images.get_approved_by_ids(req.selected_image_asset_ids)
        if len(selected_assets) != len(set(req.selected_image_asset_ids)):
            raise ValidationError(
                "All selected image assets must exist and be teacher-approved.",
                payload={
                    "selected_image_asset_ids": req.selected_image_asset_ids,
                    "approved_image_asset_ids": [asset.id for asset in selected_assets],
                },
            )

        profile = child_to_dict(child)
        interests = profile["interests"]
        reinforcers = profile["preferred_reinforcers"] or profile["reinforcers"]

        segments = build_attention_segments(
            target_skill, req.duration_minutes, profile["attention_span_minutes"]
        )
        generalization_plan = build_generalization_plan(concept)
        reinforcement_plan = build_reinforcement_plan(interests, reinforcers)
        teacher_script = self._build_teacher_script(target_skill, concept, profile)
        data_recording_sheet = self._build_data_recording_sheet(target_skill)
        session_notes_template = self._build_session_notes_template(target_skill)

        response = LessonPlanResponse(
            child_id=req.child_id,
            goal_id=goal.id if goal else None,
            teaching_goal={
                "id": goal.id if goal else None,
                "target_skill": target_skill,
                "concept": concept,
                "decision_owner": "teacher",
                "status": goal.status if goal else "draft",
                "mastery_level": goal.mastery_level if goal else 0,
            },
            target_skill=target_skill,
            duration_minutes=req.duration_minutes,
            segments=segments,
            generalization_plan=generalization_plan,
            reinforcement_plan=reinforcement_plan,
            candidate_images=[asset_to_candidate(asset) for asset in selected_assets],
            downloadable_card_pdf_links={},
            teacher_script=teacher_script,
            data_recording_sheet=data_recording_sheet,
            session_notes_template=session_notes_template,
            ai_used=False,
            cost_saving_notes=[
                "Session flow generated by deterministic attention rules; no LLM call.",
                "Generalization plan generated from rule-based dimensions; no LLM call.",
                "Reinforcement plan generated from profile interests and reinforcers; no LLM call.",
            ],
        )

        lesson = self.lessons.create(
            child_id=req.child_id,
            goal_id=goal.id if goal else None,
            target_skill=target_skill,
            duration_minutes=req.duration_minutes,
            selected_image_asset_ids=req.selected_image_asset_ids,
            package_json=response.model_dump_json(),
        )
        printable_links = PrintableCardService().generate_pdfs(
            lesson=lesson,
            assets=selected_assets,
            concept=concept,
            formats=req.print_formats,
        )
        self.lessons.update_printable_links(lesson, printable_links)
        AuditLogRepository(self.db).write(
            actor_teacher_id,
            "create",
            "LessonPackage",
            lesson.id,
            req.child_id,
            {"goal_id": lesson.goal_id, "image_count": len(selected_assets)},
        )
        response.id = lesson.id
        response.downloadable_card_pdf_links = printable_links
        return response

    def create_record(
        self, req: SessionRecordCreate, actor_teacher_id: int | None = None
    ) -> SessionRecordRead:
        child = self.children.get(req.child_id)
        if not child:
            raise NotFoundError("Child profile not found")
        goal = self.goals.get(req.goal_id) if req.goal_id is not None else None
        if req.goal_id is not None and not goal:
            raise NotFoundError("Teaching goal not found")
        if goal and goal.child_id != req.child_id:
            raise NotFoundError("Teaching goal does not belong to child profile")
        target_skill = goal.target_skill if goal else req.target_skill
        previous = self.records.latest_for_skill(
            req.child_id, target_skill, req.goal_id
        )
        previous_level = previous.mastery_level if previous else 0
        progress = evaluate_progress(
            req.independent_count, req.prompted_count, req.error_count, previous_level
        )
        record = self.records.create(
            child_id=req.child_id,
            goal_id=goal.id if goal else None,
            target_skill=target_skill,
            independent_count=req.independent_count,
            prompted_count=req.prompted_count,
            error_count=req.error_count,
            notes=req.notes,
            mastery_level=progress.mastery_level,
            progress_delta=progress.progress_delta,
            confidence_score=progress.confidence_score,
        )
        if goal:
            self.goals.update_mastery(goal, progress.mastery_level)
        AuditLogRepository(self.db).write(
            actor_teacher_id,
            "create",
            "SessionRecord",
            record.id,
            req.child_id,
            {"goal_id": record.goal_id, "mastery_level": record.mastery_level},
        )
        return SessionRecordRead(
            id=record.id,
            child_id=record.child_id,
            goal_id=record.goal_id,
            target_skill=record.target_skill,
            independent_count=record.independent_count,
            prompted_count=record.prompted_count,
            error_count=record.error_count,
            notes=record.notes,
            progress_level=record.mastery_level,
            mastery_level=record.mastery_level,
            progress_delta=record.progress_delta,
            confidence_score=record.confidence_score,
        )

    def _infer_concept(self, target_skill: str) -> str:
        # Simple local cleanup keeps common acquisition goals off the LLM path.
        for token in [
            "recognize",
            "identify",
            "label",
            "request",
            "express",
            "learn",
            "imitate",
        ]:
            target_skill = target_skill.replace(token, "")
        return target_skill.strip(" ：:，,。") or target_skill

    def _build_teacher_script(
        self, target_skill: str, concept: str, profile: dict
    ) -> list[str]:
        attention = profile.get("attention_span_minutes") or 5
        preferred = (
            profile.get("reinforcers")
            or profile.get("interests")
            or ["brief preferred activity"]
        )[0]
        return [
            f"Place the {concept} images or materials where the learner can see them, then wait for attention.",
            f"Start with one concise instruction: Today we are practicing {target_skill}.",
            "If the learner does not respond, use the lightest effective prompt first, such as a gesture or point.",
            "After an independent or close response, deliver reinforcement immediately.",
            f"About every {attention} minutes, offer a brief reinforcement or reset. Suggested option: {preferred}.",
            "After one round, change the image, object, person, or setting so learning is not tied to one material.",
        ]

    def _build_data_recording_sheet(self, target_skill: str) -> dict:
        return {
            "target_skill": target_skill,
            "fields": [
                {"key": "independent_count", "label": "Independent responses", "type": "number"},
                {"key": "prompted_count", "label": "Prompted responses", "type": "number"},
                {"key": "error_count", "label": "Errors or no responses", "type": "number"},
                {
                    "key": "used_variations",
                    "label": "Generalization variations used",
                    "type": "text",
                },
                {"key": "reinforcer_effect", "label": "Reinforcer effectiveness", "type": "text"},
                {"key": "notes", "label": "Notes", "type": "text"},
            ],
            "mastery_rule_hint": "When independent responding is 80% or higher across multiple sessions, consider increasing generalization or moving to the next goal phase.",
        }

    def _build_session_notes_template(self, target_skill: str) -> dict:
        return {
            "target_skill": target_skill,
            "sections": [
                {"key": "antecedent", "label": "What happened before the response?"},
                {"key": "prompting", "label": "Prompt level used"},
                {"key": "reinforcer_effect", "label": "Reinforcer effectiveness"},
                {"key": "generalization_used", "label": "Variations used today"},
                {"key": "teacher_decision", "label": "Next teacher decision"},
            ],
        }
