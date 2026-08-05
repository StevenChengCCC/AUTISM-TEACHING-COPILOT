from __future__ import annotations

from collections.abc import Iterable

from app.schemas.v2_dto import (
    LessonDesignDraftDto,
    LessonPackageDto,
    LessonPackageQualityScoreDto,
    QualityScoreItemDto,
)
from app.services.v2_material_blueprint_service import V2MaterialBlueprintService


class V2LessonPackageQualityService:
    """Deterministic, teacher-readable quality gate for generated lesson kits.

    The eight scores summarize existing safety, standards, material, and lesson
    structure evidence. They do not replace teacher review or claim that an AI
    image has been clinically validated.
    """

    evaluator_version = "lesson-package-quality-v2"
    placeholder_phrases = (
        "to be confirmed",
        "custom visual",
        "creating custom",
        "artwork is generating",
        "teacher review pending",
        "not set yet",
        "placeholder",
    )
    visual_material_types = {
        "quantity_cards",
        "number_cards",
        "visual_card",
        "scenario_cards",
        "sequence_cards",
        "social_narrative",
        "core_word_board",
        "visual_schedule",
        "task_analysis_cards",
        "emotion_scale",
        "sorting_page",
        "matching_page",
        "choice_board",
        "first_then_board",
        "help_card",
        "break_card",
        "teacher_cue_card",
        "token_board",
    }

    def evaluate(
        self,
        draft: LessonDesignDraftDto,
        package: LessonPackageDto,
    ) -> LessonPackageQualityScoreDto:
        items = [
            self._goal_score(draft, package),
            self._materials_score(draft, package),
            self._teaching_flow_score(package),
            self._communication_score(package),
            self._visual_semantics_score(package),
            self._dignity_score(draft, package),
            self._data_alignment_score(draft, package),
            self._low_prep_score(package),
        ]
        total = sum(item.score for item in items)
        critical_zero = any(item.critical and item.score == 0 for item in items)
        if critical_zero or total < 10:
            status = "blocked"
        elif total >= 14:
            status = "pass"
        else:
            status = "needs_review"
        return LessonPackageQualityScoreDto(
            totalScore=total,
            percentage=round(total / 16 * 100),
            overallStatus=status,
            items=items,
            evaluatorVersion=self.evaluator_version,
            teacherReviewRequired=True,
        )

    @staticmethod
    def _item(
        *,
        item_id: str,
        label: str,
        score: int,
        explanation: str,
        evidence: Iterable[str] = (),
        issues: Iterable[str] = (),
        edits: Iterable[str] = (),
        critical: bool = False,
    ) -> QualityScoreItemDto:
        return QualityScoreItemDto(
            id=item_id,
            label=label,
            score=score,
            status=("pass" if score == 2 else "needs_review" if score == 1 else "blocked"),
            explanation=explanation,
            evidence=list(evidence),
            issues=list(issues),
            recommendedEdits=list(edits),
            critical=critical,
        )

    def _goal_score(
        self, draft: LessonDesignDraftDto, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        observable = bool(
            package.goal.strip()
            and (package.observableResponse or draft.observableResponse).strip()
        )
        measurable = bool(
            draft.opportunities > 0
            and package.successCriterion.strip()
            and "required" not in package.successCriterion.lower()
            and package.baseline.strip()
            and "unknown" not in package.baseline.lower()
        )
        score = 2 if observable and measurable else 1 if observable else 0
        return self._item(
            item_id="observable-measurable-goal",
            label="Observable, measurable goal",
            score=score,
            explanation=(
                "The target response, baseline, and planned opportunities are explicit."
                if score == 2
                else "The response is observable, but baseline or success criteria still need teacher confirmation."
                if score == 1
                else "The package does not yet define an observable learner response."
            ),
            evidence=[
                f"Observable response: {package.observableResponse or 'not specified'}",
                f"Planned opportunities: {draft.opportunities}",
            ],
            issues=[] if score == 2 else ["Baseline or measurable success criterion is incomplete."],
            edits=[] if score == 2 else ["Confirm the current baseline and a measurable success criterion."],
            critical=True,
        )

    def _materials_score(
        self, draft: LessonDesignDraftDto, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        types = [material.type for material in package.materials]
        missing = V2MaterialBlueprintService.missing_from_bundle(draft, types)
        specified = sum(material.specification is not None for material in package.materials)
        if package.materials and not missing and specified == len(package.materials):
            score = 2
        elif package.materials:
            score = 1
        else:
            score = 0
        return self._item(
            item_id="complete-material-kit",
            label="Complete material kit",
            score=score,
            explanation=(
                "The goal-aligned core bundle and printable specifications are present."
                if score == 2
                else "Some materials exist, but the goal-aligned core bundle or specifications are incomplete."
                if score == 1
                else "No usable classroom materials were generated."
            ),
            evidence=[f"{len(package.materials)} generated materials"],
            issues=[f"Missing: {', '.join(missing)}"] if missing else [],
            edits=["Generate the missing core materials before approval."] if missing else [],
            critical=True,
        )

    def _teaching_flow_score(
        self, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        complete_steps = [
            step
            for step in package.teachingFlow
            if step.title.strip()
            and step.teacherAction.strip()
            and step.learnerAction.strip()
        ]
        phases = " ".join(
            f"{step.phase} {step.title}".lower() for step in package.teachingFlow
        )
        required_phases = all(
            term in phases for term in ("model", "guided", "independent")
        )
        score = (
            2
            if len(complete_steps) >= 4 and required_phases
            else 1
            if complete_steps
            else 0
        )
        return self._item(
            item_id="accurate-teaching-steps",
            label="Accurate teaching steps",
            score=score,
            explanation=(
                "The flow includes modeling, guided practice, independent opportunity, and explicit actions."
                if score == 2
                else "The flow has usable steps but is missing a complete instructional phase."
                if score == 1
                else "The teaching flow is not classroom-actionable."
            ),
            evidence=[f"{len(complete_steps)} actionable steps"],
            issues=[] if score == 2 else ["Model, guided, and independent phases are not all explicit."],
            edits=[] if score == 2 else ["Add the missing instructional phase and teacher/learner actions."],
            critical=True,
        )

    def _communication_score(
        self, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        standards = {item.id: item.status for item in package.standardsChecks}
        access_pass = standards.get("communication-access") == "pass"
        response_formats = (
            package.generalizationPlan.responseFormats
            if package.generalizationPlan
            else []
        )
        access_options = any(
            token in " ".join(response_formats).lower()
            for token in ("aac", "gesture", "picture", "sign")
        )
        modality = bool(package.responseModality.strip())
        score = 2 if modality and access_pass and access_options else 1 if modality else 0
        return self._item(
            item_id="communication-access",
            label="Supports communication mode",
            score=score,
            explanation=(
                "The learner's response mode is preserved with accessible alternatives."
                if score == 2
                else "A response mode is named, but accessible alternatives need confirmation."
                if score == 1
                else "The package does not specify an accessible response mode."
            ),
            evidence=[f"Response modality: {package.responseModality or 'not specified'}"],
            issues=[] if score == 2 else ["Communication access is not fully documented."],
            edits=[] if score == 2 else ["Confirm speech, AAC, gesture, sign, pointing, or picture responses that must be honored."],
            critical=True,
        )

    def _visual_semantics_score(
        self, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        visual_materials = [
            material
            for material in package.materials
            if material.type in self.visual_material_types
        ]
        if not visual_materials:
            return self._item(
                item_id="image-text-alignment",
                label="Image and text alignment",
                score=0,
                explanation="No visual material is available to evaluate.",
                issues=["The kit is missing a visual support."],
                edits=["Add a goal-aligned visual material."],
                critical=True,
            )
        planned = 0
        ready = 0
        exemplar_ids: set[str] = set()
        exemplar_images: set[str] = set()
        child_facing_placeholders = False
        for material in visual_materials:
            raw_items = material.content.get("visualItems")
            items = raw_items if isinstance(raw_items, list) else []
            valid_items = [
                item
                for item in items
                if isinstance(item, dict)
                and str(item.get("concept") or "").strip()
                and (
                    str(item.get("label") or "").strip()
                    or str(item.get("imageAltText") or "").strip()
                    or str(item.get("prompt") or "").strip()
                )
            ]
            if items and len(valid_items) == len(items):
                planned += 1
            if valid_items and all(
                (item.get("imageUrl") or item.get("imageBase64"))
                and item.get("generationStatus") not in {"pending", "processing", "failed"}
                for item in valid_items
            ):
                ready += 1
            for item in valid_items:
                if str(item.get("assetRole") or item.get("role") or "") != "concept_exemplar":
                    continue
                exemplar_id = str(item.get("id") or "").strip()
                image_ref = str(
                    item.get("imageUrl") or item.get("imageBase64") or ""
                ).strip()
                if exemplar_id:
                    exemplar_ids.add(exemplar_id)
                if image_ref:
                    exemplar_images.add(image_ref)
            child_facing_placeholders = (
                child_facing_placeholders
                or self._contains_placeholder(material.content)
            )
        varied_exemplars_ready = (
            not exemplar_ids
            or (len(exemplar_ids) >= 3 and len(exemplar_images) >= 3)
        )
        score = (
            2
            if (
                ready == len(visual_materials)
                and varied_exemplars_ready
                and not child_facing_placeholders
            )
            else 1
            if planned == len(visual_materials)
            else 0
        )
        return self._item(
            item_id="image-text-alignment",
            label="Image and text alignment",
            score=score,
            explanation=(
                "Every visual has a ready asset, an explicit concept/label contract, and no child-facing placeholder copy."
                if score == 2
                else "Visual concepts are planned, but final artwork, varied exemplars, or child-facing copy still needs review."
                if score == 1
                else "One or more visuals lack an explicit semantic contract."
            ),
            evidence=[
                f"{planned}/{len(visual_materials)} visuals have semantic plans",
                f"{ready}/{len(visual_materials)} visuals have ready assets",
                f"{len(exemplar_images)} distinct concept exemplars are ready",
            ],
            issues=[]
            if score == 2
            else [
                "Final visual meaning, exemplar variety, or child-facing wording is incomplete."
            ],
            edits=[]
            if score == 2
            else [
                "Use at least three meaningfully different exemplars when teaching a concept and remove all placeholder text before printing."
            ],
            critical=True,
        )

    def _dignity_score(
        self, draft: LessonDesignDraftDto, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        standards = {item.id: item.status for item in package.standardsChecks}
        safety_pass = bool(package.safetyReview and package.safetyReview.status == "pass")
        dignity_pass = standards.get("learner-dignity") == "pass"
        pause_plan = bool(
            package.teacherAdaptation and package.teacherAdaptation.signsToPause
        )
        choice_or_limits = bool(
            draft.promptingLimits.strip()
            or (
                package.reinforcementPlan
                and package.reinforcementPlan.learnerChoice.strip()
            )
        )
        score = (
            2
            if safety_pass and dignity_pass and pause_plan and choice_or_limits
            else 1
            if safety_pass
            else 0
        )
        return self._item(
            item_id="dignity-choice-sensory",
            label="Dignity, choice, and sensory needs",
            score=score,
            explanation=(
                "The plan preserves choice, communication access, pause criteria, and non-coercive support."
                if score == 2
                else "No blocked safety issue was found, but choice or sensory adaptations need confirmation."
                if score == 1
                else "A safety or dignity concern blocks classroom approval."
            ),
            evidence=[
                f"Safety status: {package.safetyReview.status if package.safetyReview else 'missing'}"
            ],
            issues=[] if score == 2 else ["Teacher review of choice, break, or sensory support is required."],
            edits=[] if score == 2 else ["Add learner choice, signs to pause, and sensory adaptations."],
            critical=True,
        )

    def _data_alignment_score(
        self, draft: LessonDesignDraftDto, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        data_material = next(
            (item for item in package.materials if item.type == "data_sheet"), None
        )
        spec = package.dataSheetSpecification
        normalized_columns = [
            str(column).strip().lower().replace("_", " ")
            for column in (spec.columns if spec else [])
        ]
        joined_columns = " ".join(normalized_columns)
        captures_response = any(
            token in joined_columns for token in ("response", "outcome", "correct")
        )
        captures_independence = any(
            token in joined_columns
            for token in ("prompt", "independence", "independent")
        )
        captures_context = any(
            token in joined_columns
            for token in ("note", "context", "setting", "scenario")
        )
        aligned = bool(
            data_material
            and spec
            and spec.columns
            and draft.dataCollection.strip()
            and package.observableResponse.strip()
            and captures_response
            and captures_independence
            and captures_context
        )
        score = 2 if aligned else 1 if data_material or spec else 0
        return self._item(
            item_id="goal-aligned-data-sheet",
            label="Data sheet aligns to goal",
            score=score,
            explanation=(
                "The data sheet records the target response, independence, prompting, and outcome."
                if score == 2
                else "A data component exists but is not fully tied to the observable response."
                if score == 1
                else "The kit does not include a goal-aligned data sheet."
            ),
            evidence=[
                f"Data sheet: {'present' if data_material else 'missing'}",
                f"Tracking columns: {len(spec.columns) if spec else 0}",
            ],
            issues=[] if score == 2 else ["Goal-to-data alignment is incomplete."],
            edits=[] if score == 2 else ["Add response outcome, independence, prompt level, and notes columns tied to the goal."],
            critical=True,
        )

    def _low_prep_score(
        self, package: LessonPackageDto
    ) -> QualityScoreItemDto:
        specified = [
            material
            for material in package.materials
            if material.specification is not None
        ]
        teacher_ready = [
            material
            for material in specified
            if material.specification
            and material.specification.printPreparation
            and material.specification.teacherDirections
            and material.specification.editableFields
        ]
        ready = bool(
            package.preparationChecklist
            and package.materials
            and len(teacher_ready) == len(package.materials)
            and not self._contains_placeholder(package.documentContent)
            and not any(
                self._contains_placeholder(material.content)
                for material in package.materials
            )
        )
        score = 2 if ready else 1 if package.preparationChecklist or specified else 0
        return self._item(
            item_id="low-prep-usability",
            label="Ready with low prep",
            score=score,
            explanation=(
                "Every material includes print preparation, editable fields, and concise teacher directions."
                if score == 2
                else "The kit is usable, but one or more materials still require teacher setup."
                if score == 1
                else "The package lacks practical preparation guidance."
            ),
            evidence=[
                f"{len(teacher_ready)}/{len(package.materials)} materials are fully specified"
            ],
            issues=[] if score == 2 else ["Some material preparation steps are missing."],
            edits=[] if score == 2 else ["Add one-page print preparation and teacher-use directions for every material."],
        )

    @classmethod
    def _contains_placeholder(cls, value: object) -> bool:
        if isinstance(value, str):
            normalized = " ".join(value.lower().split())
            return any(phrase in normalized for phrase in cls.placeholder_phrases)
        if isinstance(value, dict):
            return any(cls._contains_placeholder(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(cls._contains_placeholder(item) for item in value)
        return False
