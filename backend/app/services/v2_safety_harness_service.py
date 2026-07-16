from __future__ import annotations

import json
import re
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
    version: str
    terms: tuple[str, ...]
    explanation: str
    recommended_edit: str

    def matches(self, text: str) -> list[str]:
        normalized = " ".join(text.casefold().split())
        return [
            term
            for term in self.terms
            if re.search(rf"(?<!\w){re.escape(term.casefold())}(?!\w)", normalized)
        ]


class V2SafetyHarnessService:
    """Deterministic instructional safety boundary, not a clinical review."""

    evaluator_version = "instructional-safety-v1"
    rules = (
        SafetyRule(
            "no-punishment-humiliation",
            evaluator_version,
            ("punishment", "humiliate", "humiliation", "shame the learner"),
            "Punitive or humiliating practices are not appropriate lesson supports.",
            "Use neutral feedback, learner choice, and supportive re-teaching.",
        ),
        SafetyRule(
            "no-deprivation",
            evaluator_version,
            ("withhold food", "deprive", "deprivation", "earn access to water"),
            "Basic needs and essential communication access cannot be contingent rewards.",
            "Use non-coercive, teacher-confirmed engagement supports.",
        ),
        SafetyRule(
            "communication-access",
            evaluator_version,
            ("remove aac", "take away aac", "withhold communication device"),
            "AAC and communication access must remain available.",
            "Keep the learner's established communication modes available throughout.",
        ),
        SafetyRule(
            "no-forced-compliance",
            evaluator_version,
            (
                "forced eye contact",
                "force eye contact",
                "unnecessary physical prompt",
                "hand over hand until",
                "force the learner",
                "physically force",
                "suppress stimming",
                "stop harmless stimming",
            ),
            "The plan must preserve dignity, bodily autonomy, and harmless self-regulation.",
            "Offer alternatives, pause, and seek team guidance when support needs change.",
        ),
        SafetyRule(
            "no-restrictive-aversive-practice",
            evaluator_version,
            ("restraint", "seclusion", "aversive", "pain compliance"),
            "Restrictive or aversive practices are outside lesson-kit generation.",
            "Block generation and refer the request to authorized team procedures.",
        ),
        SafetyRule(
            "no-clinical-claims",
            evaluator_version,
            (
                "diagnose",
                "diagnosis is",
                "cure autism",
                "medical treatment",
                "guaranteed treatment outcome",
                "clinical recommendation",
            ),
            "The product cannot diagnose, promise a cure, or recommend medical treatment.",
            "Keep content instructional and defer clinical decisions to qualified professionals.",
        ),
    )

    @staticmethod
    def _text(draft: LessonDesignDraftDto, generated_content: dict) -> str:
        # This value is never logged. JSON serialization gives deterministic rule input.
        return " ".join(
            [
                draft.goalText,
                draft.customNotes,
                draft.promptingStart,
                draft.promptingLimits,
                draft.reinforcementPlan,
                draft.errorCorrection,
                draft.teacherConstraints,
                json.dumps(generated_content, sort_keys=True, default=str),
            ]
        )

    def review(self, draft: LessonDesignDraft, generated_text: str) -> SafetyReport:
        product_draft = LessonDesignDraftDto.model_validate(
            draft.model_dump(mode="json", by_alias=True)
        )
        review = self.review_product(product_draft, {"generatedText": generated_text})
        checks = [
            CheckResult(
                id=f"safety-{index}",
                category="learner_safety",
                passed=review.status != "blocked",
                severity="blocking" if review.status == "blocked" else "info",
                message=issue,
            )
            for index, issue in enumerate(review.issues or ["Safety rules passed"], 1)
        ]
        return SafetyReport(passed=review.status != "blocked", checks=checks)

    def review_product(
        self, draft: LessonDesignDraftDto, generated_content: dict
    ) -> SafetyReviewDto:
        text = self._text(draft, generated_content)
        matches: list[tuple[SafetyRule, list[str]]] = []
        for rule in self.rules:
            terms = rule.matches(text)
            if terms:
                matches.append((rule, terms))
        if matches:
            return SafetyReviewDto(
                status="blocked",
                riskLevel="high",
                issues=[
                    f"{rule.id} ({rule.version}): {rule.explanation}"
                    for rule, _terms in matches
                ],
                recommendedEdits=[rule.recommended_edit for rule, _terms in matches],
                appliedEdits=[],
            )
        return SafetyReviewDto(
            status="pass",
            riskLevel="low",
            issues=[],
            recommendedEdits=[],
            appliedEdits=[
                "Checked learner dignity and communication access.",
                "Checked for punitive, coercive, restrictive, and aversive practices.",
                "Checked for unsupported diagnostic, cure, and medical claims.",
            ],
        )
