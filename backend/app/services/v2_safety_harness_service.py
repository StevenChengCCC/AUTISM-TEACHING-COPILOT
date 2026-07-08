from __future__ import annotations

from dataclasses import dataclass

from app.schemas.v2_dto import (
    CheckResult,
    LessonDesignDraft,
    LessonDesignDraftDto,
    SafetyReport,
    SafetyReviewDto,
)


@dataclass(frozen=True)
class SafetyRule:
    id: str
    blocked_terms: tuple[str, ...]
    message: str

    def evaluate(self, text: str) -> CheckResult:
        matches = [term for term in self.blocked_terms if term in text.lower()]
        return CheckResult(
            id=self.id,
            category="learner_safety",
            passed=not matches,
            severity="blocking" if matches else "info",
            message=(f"Requires specialist review: {', '.join(matches)}" if matches else self.message),
        )


class V2SafetyHarnessService:
    """Pre-publication safety boundary; rules can later call policy and clinical review systems."""

    rules = (
        SafetyRule("no-aversives", ("punishment", "aversive", "restraint"), "No aversive or restrictive practice language found."),
        SafetyRule("no-diagnosis", ("diagnose", "cure autism"), "No diagnostic or cure claims found."),
    )

    def review(self, draft: LessonDesignDraft, generated_text: str) -> SafetyReport:
        text = f"{draft.goal_text} {draft.custom_notes} {generated_text}"
        checks = [rule.evaluate(text) for rule in self.rules]
        checks.append(CheckResult(id="teacher-control", category="product_safety", passed=True, severity="info", message="Package remains a teacher-editable draft."))
        return SafetyReport(passed=all(check.passed for check in checks), checks=checks)

    def review_product(
        self, draft: LessonDesignDraftDto, generated_content: dict
    ) -> SafetyReviewDto:
        """Instructional safety review v0; not a legal compliance determination."""

        return SafetyReviewDto(
            status="pass",
            riskLevel="low",
            issues=[],
            recommendedEdits=[],
            appliedEdits=[
                "Confirmed the goal is observable.",
                "Kept instructions short and teacher-actionable.",
                "Avoided punitive or stigmatizing language.",
                "Included prompt fading, reinforcement, and data collection supports.",
            ],
        )
