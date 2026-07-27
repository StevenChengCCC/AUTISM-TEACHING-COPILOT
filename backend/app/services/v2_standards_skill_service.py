from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from app.schemas.v2_dto import (
    CheckResult,
    GeneratedMaterialDto,
    LessonDesignDraft,
    LessonDesignDraftDto,
    StandardsCheckDto,
    StandardsReport,
)
from app.skills.registry import SkillRegistry, get_skill_registry
from app.services.v2_material_blueprint_service import V2MaterialBlueprintService


QualityContext = tuple[LessonDesignDraftDto, list[GeneratedMaterialDto], dict]


@dataclass(frozen=True)
class InstructionalQualityRule:
    id: str
    version: str
    severity: str
    label: str
    evidence_location: str
    explanation: str
    recommended_edit: str
    check: Callable[[QualityContext], bool | None]

    def evaluate(self, context: QualityContext) -> StandardsCheckDto:
        result = self.check(context)
        status = (
            "not_applicable"
            if result is None
            else (
                "pass"
                if result
                else ("blocked" if self.severity == "high" else "needs_review")
            )
        )
        return StandardsCheckDto(
            id=self.id,
            skillId="instructional-quality",
            label=self.label,
            description=self.explanation,
            severity=self.severity,
            status=status,
            recommendation=self.recommended_edit,
            version=self.version,
            evidenceLocation=self.evidence_location,
            explanation=self.explanation,
            recommendedEdit=self.recommended_edit,
        )


def _package_text(context: QualityContext) -> str:
    draft, _materials, generated = context
    return " ".join(
        [
            draft.goalText,
            draft.errorCorrection,
            draft.reinforcementPlan,
            draft.promptingStart,
            draft.promptingLimits,
            str(generated),
        ]
    ).casefold()


def _contains_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    """Match whole words/phrases so `force` does not match `reinforcement`."""

    return any(
        re.search(rf"(?<!\w){re.escape(phrase.casefold())}(?!\w)", text)
        for phrase in phrases
    )


class V2StandardsSkillService:
    """Versioned deterministic instructional quality evaluator."""

    evaluator_version = "instructional-quality-v1"
    ny_skill_id = "ny_instructional_materials"
    image_material_types = {
        "quantity_cards",
        "visual_card",
        "choice_board",
        "first_then_board",
        "help_card",
        "break_card",
        "token_board",
        "sorting_page",
        "matching_page",
        "scenario_cards",
        "visual_schedule",
        "task_analysis_cards",
        "emotion_scale",
        "teacher_cue_card",
    }
    rules = (
        InstructionalQualityRule(
            "observable-goal",
            evaluator_version,
            "high",
            "Observable goal",
            "goal",
            "The goal must describe an observable learner response.",
            "Rewrite the goal using a visible or countable learner action and confirm it.",
            lambda c: bool(c[0].goalText.strip())
            and any(
                word in c[0].goalText.casefold()
                for word in ("will", "requests", "selects", "matches", "sorts", "uses")
            ),
        ),
        InstructionalQualityRule(
            "goal-flow-data-alignment",
            evaluator_version,
            "high",
            "Goal, flow, and data alignment",
            "teachingFlow,dataSheetSpecification",
            "Practice and data collection must measure the confirmed target response.",
            "Align opportunity definitions and data columns to the observable response.",
            lambda c: bool(c[2].get("teachingFlow"))
            and bool(c[0].dataCollection.strip()),
        ),
        InstructionalQualityRule(
            "appropriate-prompting",
            evaluator_version,
            "medium",
            "Appropriate prompting",
            "promptingPlan",
            "The package must state a starting prompt and preserve teacher override.",
            "Add a starting prompt, wait time, limits, and teacher override.",
            lambda c: bool(
                c[0].promptingStart.strip() and c[0].promptingLimits.strip()
            ),
        ),
        InstructionalQualityRule(
            "prompt-fading",
            evaluator_version,
            "medium",
            "Prompt fading",
            "promptingPlan",
            "The plan should state an intention to reduce support when appropriate.",
            "Add observable criteria for reducing prompt support.",
            lambda c: _contains_any_phrase(
                _package_text(c), ("fade", "least-to-most", "reduce support")
            ),
        ),
        InstructionalQualityRule(
            "neutral-error-correction",
            evaluator_version,
            "high",
            "Neutral error correction",
            "errorCorrectionPlan",
            "Errors must receive neutral feedback and another supported opportunity.",
            "Replace punitive language with neutral feedback, modeling, and retry.",
            lambda c: "neutral" in c[0].errorCorrection.casefold()
            and not _contains_any_phrase(_package_text(c), ("punishment", "shame")),
        ),
        InstructionalQualityRule(
            "reinforcement-logic",
            evaluator_version,
            "high",
            "Reinforcement and engagement",
            "reinforcementPlan",
            "Engagement support must follow the target response and avoid deprivation.",
            "State delivery timing, learner choice, and a non-coercive alternative.",
            lambda c: bool(c[0].reinforcementPlan.strip())
            and not _contains_any_phrase(
                _package_text(c), ("deprive", "withhold food")
            ),
        ),
        InstructionalQualityRule(
            "communication-access",
            evaluator_version,
            "high",
            "Communication access",
            "responseModality",
            "The learner's selected response modality must remain available.",
            "Name the accepted speech, gesture, picture, or AAC response options.",
            lambda c: bool(c[0].responseLevel.strip()),
        ),
        InstructionalQualityRule(
            "learner-dignity",
            evaluator_version,
            "high",
            "Learner dignity",
            "wholePackage",
            "Language and procedures must preserve autonomy and dignity.",
            "Remove coercive, stigmatizing, or compliance-only language.",
            lambda c: not _contains_any_phrase(
                _package_text(c),
                ("noncompliant", "defiant", "force", "humiliate"),
            ),
        ),
        InstructionalQualityRule(
            "age-respectfulness",
            evaluator_version,
            "medium",
            "Age respectfulness",
            "materials",
            "Materials should be respectful rather than infantilizing.",
            "Use age-neutral visuals and interests confirmed by the teacher.",
            lambda c: not _contains_any_phrase(
                _package_text(c), ("for babies", "toddler-only", "babyish")
            ),
        ),
        InstructionalQualityRule(
            "generalization",
            evaluator_version,
            "medium",
            "Generalization and maintenance",
            "generalizationPlan",
            "The plan should vary examples, people, settings, or materials gradually.",
            "Add at least two relevant and familiar generalization dimensions.",
            lambda c: bool(c[0].generalizationPlan.strip())
            and len(c[0].scenarios) >= 2,
        ),
        InstructionalQualityRule(
            "material-usability",
            evaluator_version,
            "medium",
            "Material usability",
            "materials",
            "Every material should have a typed, print-aware specification.",
            "Add purpose, audience, layout, text limits, print checks, and editable fields.",
            lambda c: bool(c[1])
            and all(item.specification is not None for item in c[1]),
        ),
        InstructionalQualityRule(
            "teacher-editability",
            evaluator_version,
            "medium",
            "Teacher editability",
            "materials",
            "Generated supports must expose fields the teacher can adapt.",
            "Expose editable wording, examples, prompt levels, and reinforcement fields.",
            lambda c: bool(c[1])
            and all(
                item.specification is not None
                and bool(item.specification.editableFields)
                for item in c[1]
            ),
        ),
        InstructionalQualityRule(
            "no-invented-learner-information",
            evaluator_version,
            "high",
            "No invented learner information",
            "personalizationSources",
            "Personalization must use confirmed or sufficiently supported profile data.",
            "Remove unsupported preferences or mark them as teacher-confirmation needed.",
            lambda c: not bool(c[2].get("inventedLearnerDetails")),
        ),
    )

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._registry = registry or get_skill_registry()
        self._ny_skill = self._registry.get(self.ny_skill_id)

    def _ny_check(
        self,
        *,
        check_id: str,
        label: str,
        description: str,
        severity: str,
        status: str,
        recommendation: str,
        evidence_location: str,
    ) -> StandardsCheckDto:
        manifest = self._ny_skill.manifest
        return StandardsCheckDto(
            id=check_id,
            skillId=manifest.skill_id,
            label=label,
            description=description,
            severity=severity,
            status=status,
            recommendation=recommendation,
            version=manifest.evaluator_version,
            evidenceLocation=evidence_location,
            explanation=description,
            recommendedEdit=recommendation,
        )

    def _evaluate_ny_materials(
        self,
        draft: LessonDesignDraftDto,
        materials: list[GeneratedMaterialDto],
    ) -> list[StandardsCheckDto]:
        material_types = {material.type for material in materials}
        missing_bundle_items = V2MaterialBlueprintService.missing_from_bundle(
            draft, material_types
        )
        has_complete_specs = bool(materials) and all(
            material.specification is not None for material in materials
        ) and not missing_bundle_items
        completeness_status = (
            "not_applicable"
            if not materials
            else ("pass" if has_complete_specs else "blocked")
        )
        visual_materials = [
            material
            for material in materials
            if material.type in self.image_material_types
        ]
        has_visual_plans = not visual_materials or all(
            isinstance(material.content.get("visualItems"), list)
            and bool(material.content["visualItems"])
            for material in visual_materials
        )
        print_ready = bool(materials) and all(
            material.specification is not None
            and bool(material.specification.printPreparation)
            and bool(material.specification.contrastGuidance.strip())
            and bool(material.specification.margins.strip())
            for material in materials
        )
        return [
            self._ny_check(
                check_id="ny-complete-material-kit",
                label="Complete classroom material kit",
                description=(
                    "Every goal-family kit needs all required materials plus a typed, "
                    "editable classroom-ready specification for each item."
                ),
                severity="high",
                status=completeness_status,
                recommendation=(
                    "Generate the complete goal-family bundle and concise teacher "
                    "directions for every material. Missing: "
                    + (", ".join(missing_bundle_items) or "none")
                ),
                evidence_location="materials",
            ),
            self._ny_check(
                check_id="ny-visual-set-plan",
                label="Complete visual set plan",
                description=(
                    "Each visual material needs an explicit item-level artwork plan so "
                    "multi-card and sequence activities cannot silently omit images."
                ),
                severity="high",
                status="pass" if has_visual_plans else "blocked",
                recommendation=(
                    "Create one planned visual item for every card, choice, sequence "
                    "step, or countable unit before image generation."
                ),
                evidence_location="materials.visualItems",
            ),
            self._ny_check(
                check_id="ny-print-readiness",
                label="Print-ready specifications",
                description=(
                    "Material specifications need margins, contrast guidance, and "
                    "actual-size print preparation."
                ),
                severity="medium",
                status=(
                    "not_applicable"
                    if not materials
                    else ("pass" if print_ready else "needs_review")
                ),
                recommendation=(
                    "Add print-safe margins, high-contrast guidance, and an actual-size "
                    "review step."
                ),
                evidence_location="materials.specification",
            ),
            self._ny_check(
                check_id="ny-communication-and-at-access",
                label="Communication and access preserved",
                description=(
                    "The confirmed response mode and assistive access must remain "
                    "available in instruction and materials."
                ),
                severity="high",
                status="pass" if bool(draft.responseLevel.strip()) else "blocked",
                recommendation=(
                    "Confirm and preserve speech, AAC, picture, sign, gesture, writing, "
                    "or device access as appropriate."
                ),
                evidence_location="responseLevel,materials",
            ),
            self._ny_check(
                check_id="ny-curriculum-alignment-review",
                label="New York curriculum alignment",
                description=(
                    "Grade, subject, and New York learning-standard alignment require "
                    "teacher confirmation and must not be guessed from disability data."
                ),
                severity="medium",
                status="needs_review",
                recommendation=(
                    "Let the teacher select or confirm the relevant New York standard "
                    "when standards alignment is needed."
                ),
                evidence_location="teacher_review",
            ),
        ]

    def evaluate(
        self, draft: LessonDesignDraft, jurisdiction: str = "generic-us"
    ) -> StandardsReport:
        product = LessonDesignDraftDto.model_validate(
            draft.model_dump(mode="json", by_alias=True)
        )
        checks = self.evaluate_product(product, [], {})
        return StandardsReport(
            jurisdiction=jurisdiction,
            framework="Lesson Kit Studio instructional quality v1",
            checks=[
                CheckResult(
                    id=item.id,
                    category="instructional_quality",
                    passed=item.status in {"pass", "not_applicable"},
                    severity="blocking" if item.status == "blocked" else "warning",
                    message=item.explanation,
                )
                for item in checks
            ],
        )

    def evaluate_product(
        self,
        draft: LessonDesignDraftDto,
        materials: list[GeneratedMaterialDto],
        generated_content: dict | None = None,
    ) -> list[StandardsCheckDto]:
        context = (draft, materials, generated_content or {})
        return [
            *(rule.evaluate(context) for rule in self.rules),
            *self._evaluate_ny_materials(draft, materials),
        ]
