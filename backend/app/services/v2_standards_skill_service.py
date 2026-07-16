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
            and "data" in " ".join(c[0].selectedMaterials).casefold()
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
        return [rule.evaluate(context) for rule in self.rules]
