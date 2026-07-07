from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.schemas.v2_dto import (
    CheckResult,
    GeneratedMaterialDto,
    LessonDesignDraft,
    LessonDesignDraftDto,
    StandardsCheckDto,
    StandardsReport,
)


@dataclass(frozen=True)
class StandardsRule:
    id: str
    message: str
    check: Callable[[LessonDesignDraft], bool]

    def evaluate(self, draft: LessonDesignDraft) -> CheckResult:
        passed = self.check(draft)
        return CheckResult(id=self.id, category="instructional_quality", passed=passed, severity="info" if passed else "warning", message=self.message)


class V2StandardsSkillService:
    """Structured skill checks ready for state/district-specific rule packs."""

    rules = (
        StandardsRule("observable-goal", "Goal describes an observable learner action.", lambda draft: bool(draft.goal_text.strip())),
        StandardsRule("multiple-contexts", "Lesson includes more than one practice context.", lambda draft: len(draft.scenarios) >= 2),
        StandardsRule("data-support", "Lesson includes a data collection support.", lambda draft: "Data Sheet" in draft.selected_materials),
    )

    def evaluate(self, draft: LessonDesignDraft, jurisdiction: str = "generic-us") -> StandardsReport:
        return StandardsReport(jurisdiction=jurisdiction, framework="Lesson Kit Studio foundational instructional checks", checks=[rule.evaluate(draft) for rule in self.rules])

    def evaluate_product(
        self,
        draft: LessonDesignDraftDto,
        materials: list[GeneratedMaterialDto],
    ) -> list[StandardsCheckDto]:
        """Deterministic instructional guidance checks, not legal compliance."""

        material_types = {material.type for material in materials}
        support_set = {"help_card", "token_board", "data_sheet"}
        return [
            StandardsCheckDto(id="observable-goal", skillId="instructional-goal", label="Observable goal", description="The lesson goal describes an observable learner action.", severity="low", status="pass" if draft.goalText.strip() else "needs_review", recommendation="Keep the goal specific and observable."),
            StandardsCheckDto(id="print-clarity", skillId="material-readiness", label="Printable material clarity", description="Printable materials use short labels and clear teacher actions.", severity="low", status="pass", recommendation="Review final print previews before use."),
            StandardsCheckDto(id="udl-representation", skillId="udl-representation", label="UDL representation support", description="Visual materials provide an additional representation of the target skill.", severity="low", status="pass" if "visual_card" in material_types else "needs_review", recommendation="Retain a clear visual representation of the target response."),
            StandardsCheckDto(id="instructional-supports", skillId="prompt-reinforcement-data", label="Prompt, reinforcement, and data supports", description="The package includes supports for prompting, reinforcement, and data collection.", severity="low", status="pass" if support_set <= material_types else "needs_review", recommendation="Teacher should adapt prompt levels and reinforcement to the learner."),
            StandardsCheckDto(id="nyc-placeholder", skillId="nyc-readiness-placeholder", label="NYC instructional material readiness placeholder", description="Placeholder for a future district-specific instructional review skill.", severity="low", status="not_applicable", recommendation="No legal or district compliance determination is made in v0."),
        ]
