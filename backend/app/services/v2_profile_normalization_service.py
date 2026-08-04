from __future__ import annotations

from collections import defaultdict

from app.core.exceptions import ValidationError
from app.schemas.v2_dto import (
    CanonicalLearnerProfile,
    LearnerProfile,
    LearnerProfileSummary,
    ProfileFactor,
)

_SENSITIVE_NON_INSTRUCTIONAL_LABELS = (
    "school name",
    "district",
    "provider name",
    "home address",
    "family contact",
    "medical history",
    "medication",
    "location",
)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _join(values: list[str]) -> str:
    return "; ".join(_unique(values))


def _legacy_factor(signal) -> ProfileFactor:
    status = "confirmed_current" if signal.status == "confirmed" else "unconfirmed"
    category_map = {
        "interest": "current_interest",
        "reinforcer": "reinforcement",
        "communication": "communication",
        "support_need": "other",
        "sensory_preference": "sensory",
        "strength": "learning_strength",
        "prompting": "prompting",
        "generalization": "generalization",
        "receptive_support": "receptive_language",
        "attention_engagement": "attention",
        "break_preference": "regulation",
    }
    return ProfileFactor(
        id=f"factor-{signal.id}",
        category=category_map.get(signal.category, "other"),
        label=signal.label,
        value=signal.suggested_profile_value or signal.label,
        status=status,
        confidence=signal.confidence,
        sourceEvidence=signal.evidence or signal.summary or signal.label,
        sourceRecordId=signal.source_record_id,
        instructionalImplication=signal.summary or signal.label,
        generationConstraints=[],
        teacherReviewed=signal.status == "confirmed",
    )


def _is_safe_factor(factor: ProfileFactor) -> bool:
    searchable = f"{factor.label} {factor.value}".casefold()
    return not any(term in searchable for term in _SENSITIVE_NON_INSTRUCTIONAL_LABELS)


def canonicalize_profile(learner: LearnerProfile) -> LearnerProfile:
    """Validate the canonical profile and derive all compatibility fields from it."""

    supplied = learner.normalized_profile
    structured_authoritative = bool(supplied and supplied.factors)
    factors = list(supplied.factors if supplied else [])
    if not factors and learner.profile_signals:
        factors = [_legacy_factor(signal) for signal in learner.profile_signals]

    safe_factors = [factor for factor in factors if _is_safe_factor(factor)]
    ids = [factor.id for factor in safe_factors]
    if len(ids) != len(set(ids)):
        raise ValidationError("Extracted profile factor IDs must be unique.")

    grouped: dict[str, list[ProfileFactor]] = defaultdict(list)
    for factor in safe_factors:
        grouped[factor.category].append(factor)

    current = [
        factor
        for factor in safe_factors
        if factor.status
        in {"confirmed_current", "teacher_confirmed", "teacher_edited", "derived"}
        and (
            factor.status != "derived"
            or any(
                item.startswith("derived_from_confirmed_factor=")
                for item in factor.generation_constraints
            )
        )
    ]
    unconfirmed = [factor for factor in safe_factors if factor.status == "unconfirmed"]
    historical = [factor for factor in safe_factors if factor.status == "historical"]
    excluded = [
        factor
        for factor in safe_factors
        if factor.status in {"not_approved", "not_meaningful", "omitted", "rejected"}
    ]
    prohibited = [
        factor for factor in safe_factors if factor.category == "prohibited_item"
    ]
    current_by_category: dict[str, list[ProfileFactor]] = defaultdict(list)
    for factor in current:
        current_by_category[factor.category].append(factor)

    communication = _join(
        [factor.value for factor in current_by_category["communication"]]
    )
    support_categories = (
        "receptive_language",
        "sensory",
        "visual_access",
        "motor_access",
        "transition",
        "regulation",
        "prompting",
        "error_correction",
        "safety",
        "prohibited_item",
        "other",
    )
    supports = _unique(
        [
            factor.value
            for category in support_categories
            for factor in current_by_category[category]
        ]
    )
    interests = _unique(
        [factor.value for factor in current_by_category["current_interest"]]
    )
    reinforcement = _unique(
        [factor.value for factor in current_by_category["reinforcement"]]
    )
    formats = _unique(
        [
            factor.value
            for category in (
                "attention",
                "receptive_language",
                "learning_strength",
                "generalization",
            )
            for factor in current_by_category[category]
        ]
    )
    secondary = [*historical, *unconfirmed, *excluded]
    summary = LearnerProfileSummary(
        communication=communication,
        supports=supports,
        currentInterests=interests,
        learningFormat=_join(formats),
        keyTeachingNotes=_unique([factor.value for factor in secondary]),
    )
    canonical = CanonicalLearnerProfile(
        learnerId=learner.id,
        age=learner.age,
        factors=safe_factors,
        confirmedFactorIds=[factor.id for factor in current],
        unconfirmedFactorIds=[factor.id for factor in unconfirmed],
        historicalFactorIds=[factor.id for factor in historical],
        excludedFactorIds=_unique([factor.id for factor in [*prohibited, *excluded]]),
        blockingIssues=list(supplied.blocking_issues if supplied else []),
        summary=summary,
    )
    return learner.model_copy(
        update={
            "normalized_profile": canonical,
            "communication_mode": (
                communication
                if structured_authoritative
                else learner.communication_mode
            ),
            "support_needs": (
                supports if structured_authoritative else learner.support_needs
            ),
            "interests": interests if structured_authoritative else learner.interests,
            "reinforcement_preferences": (
                reinforcement
                if structured_authoritative
                else learner.reinforcement_preferences
            ),
            "attention_profile": (
                summary.learning_format
                if structured_authoritative
                else learner.attention_profile
            ),
            "notes": (
                _join(summary.key_teaching_notes)
                if structured_authoritative
                else learner.notes
            ),
        }
    )


def merge_canonical_profiles(
    current: LearnerProfile, extracted: LearnerProfile
) -> CanonicalLearnerProfile | None:
    """Add new evidence without deleting or downgrading teacher-reviewed factors."""

    current_profile = current.normalized_profile
    extracted_profile = extracted.normalized_profile
    if not current_profile and not extracted_profile:
        return None
    merged = {
        factor.id: factor
        for factor in (current_profile.factors if current_profile else [])
    }
    for factor in extracted_profile.factors if extracted_profile else []:
        previous = merged.get(factor.id)
        if previous and previous.teacher_reviewed:
            continue
        merged[factor.id] = factor
    return CanonicalLearnerProfile(
        learnerId=current.id,
        age=extracted.age,
        factors=list(merged.values()),
        blockingIssues=list(
            extracted_profile.blocking_issues if extracted_profile else []
        ),
    )
