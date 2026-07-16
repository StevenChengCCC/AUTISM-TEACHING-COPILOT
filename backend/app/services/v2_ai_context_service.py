from __future__ import annotations

import re
from typing import Any

from app.schemas.v2_dto import LearnerProfile, LessonDesignDraftDto, ProfileSignal


def _age_band(age: int) -> str:
    if age <= 0:
        return "unspecified school-age learner"
    if age <= 5:
        return "early childhood"
    if age <= 10:
        return "elementary age"
    if age <= 13:
        return "middle school age"
    return "secondary school age"


def _remove_direct_identifiers(learner: LearnerProfile, value: str) -> str:
    cleaned = value
    for identifier in {learner.code, learner.id}:
        if identifier:
            cleaned = re.sub(
                re.escape(identifier), "a fictional learner", cleaned, flags=re.I
            )
    for sensitive_fragment in [
        learner.notes,
        *[signal.evidence for signal in learner.profile_signals],
    ]:
        fragment = sensitive_fragment.strip()
        if fragment:
            cleaned = re.sub(re.escape(fragment), "", cleaned, flags=re.I)
    return " ".join(cleaned.split())


def _eligible_signals(learner: LearnerProfile) -> list[ProfileSignal]:
    return [
        signal
        for signal in learner.profile_signals
        if signal.status == "confirmed"
        or (signal.status == "suggested" and signal.confidence >= 0.75)
    ]


def _signal_labels(
    learner: LearnerProfile, category: str, *, confirmed_only: bool = False
) -> list[str]:
    return list(
        dict.fromkeys(
            signal.label
            for signal in learner.profile_signals
            if signal.category == category
            and (
                signal.status == "confirmed"
                or (
                    not confirmed_only
                    and signal.status == "suggested"
                    and signal.confidence >= 0.75
                )
            )
        )
    )


def build_ai_safe_profile(learner: LearnerProfile) -> dict[str, Any]:
    """Return minimum teaching context without record text or direct identity data."""

    reviewed = learner.profile_review_status == "confirmed"
    interests = learner.interests if reviewed else _signal_labels(learner, "interest")
    reinforcers = (
        learner.reinforcement_preferences
        if reviewed
        else _signal_labels(learner, "reinforcer")
    )
    return {
        "ageBand": _age_band(learner.age),
        "communicationMode": learner.communication_mode,
        "attentionProfile": learner.attention_profile,
        "interests": interests,
        "reinforcementPreferences": reinforcers,
        "supportNeeds": learner.support_needs,
        "strengths": learner.strengths,
        "sensoryPreferences": learner.sensory_preferences,
        "knownChallenges": learner.known_challenges,
        "promptingPreferences": learner.prompting_preferences,
        "currentGoals": learner.current_goals,
        "readingLevel": learner.reading_level,
        "activityDurationPreference": learner.activity_duration_preference,
        "profileSignals": [
            {
                "category": signal.category,
                "label": signal.label,
                "confidence": signal.confidence,
                "status": signal.status,
            }
            for signal in _eligible_signals(learner)
        ],
    }


def build_lesson_generation_context(
    learner: LearnerProfile, draft: LessonDesignDraftDto
) -> dict[str, Any]:
    safe = build_ai_safe_profile(learner)
    return {
        **safe,
        "teacherConfirmedDraft": {
            "goalText": draft.goalText,
            "responseLevel": draft.responseLevel,
            "scenarios": draft.scenarios,
            "selectedMaterials": draft.selectedMaterials,
            "theme": draft.theme,
            "duration": draft.duration,
            "customNotes": draft.customNotes,
        },
        "neutralThemeRequired": not bool(
            learner.interests or _signal_labels(learner, "interest")
        ),
    }


def build_image_generation_context(
    learner: LearnerProfile, material_type: str, concept: str
) -> dict[str, Any]:
    confirmed_interests = _signal_labels(learner, "interest", confirmed_only=True)
    suggested_interests = [
        label
        for label in _signal_labels(learner, "interest")
        if label not in confirmed_interests
    ]
    legacy_interests = (
        learner.interests if learner.profile_review_status == "confirmed" else []
    )
    interest_theme = next(
        iter([*confirmed_interests, *legacy_interests, *suggested_interests]), None
    )
    return {
        "ageBand": _age_band(learner.age),
        "concept": _remove_direct_identifiers(learner, concept.strip()),
        "materialType": material_type,
        "interestTheme": interest_theme,
        "sensoryVisualPreferences": learner.sensory_preferences,
        "communicationSupport": learner.communication_mode,
        "neutralFallbackTheme": interest_theme is None,
    }


def build_safe_image_prompt(
    learner: LearnerProfile,
    material_type: str,
    concept: str,
    provider_prompt: str = "",
) -> tuple[str, str]:
    """Build a low-clutter prompt from minimized context and remove identifiers."""

    context = build_image_generation_context(learner, material_type, concept)

    safe_concept = context["concept"] or "a common classroom activity"
    theme = context["interestTheme"]
    if theme:
        theme_clause = (
            f"Use a subtle {theme} interest theme when it supports the concept."
        )
    else:
        theme_clause = (
            "Use neutral classroom materials such as blocks, pencils, or books."
        )
    support_clause = (
        f"Communication support: {context['communicationSupport']}."
        if context["communicationSupport"]
        else "Use a clear, observable classroom interaction."
    )
    cleaned_provider_prompt = _remove_direct_identifiers(learner, provider_prompt)
    optional_direction = (
        f" Provider direction: {cleaned_provider_prompt}"
        if cleaned_provider_prompt
        else ""
    )
    prompt = (
        f"Create a low-clutter printable {material_type.replace('_', ' ')} showing "
        f"{safe_concept}. Show only fictional, non-identifying people. {theme_clause} "
        f"{support_clause} Do not include names, learner codes, diagnoses, logos, branded "
        f"characters, record text, or embedded text. Teacher review is required."
        f"{optional_direction}"
    )
    alt_text = f"Teacher-reviewable classroom illustration showing {safe_concept}."
    return prompt, alt_text


def personalization_sources(
    learner: LearnerProfile, draft: LessonDesignDraftDto
) -> list[str]:
    sources = ["teacher goal"]
    if learner.communication_mode:
        sources.append("communication mode")
    if learner.support_needs:
        sources.append("support needs")
    if (
        learner.profile_review_status == "confirmed"
        and learner.reinforcement_preferences
    ):
        sources.append("reinforcement preferences")
    if learner.prompting_preferences:
        sources.append("prompting preferences")
    if (
        learner.profile_review_status == "confirmed" and learner.interests
    ) or _signal_labels(learner, "interest"):
        sources.append("confirmed or high-confidence interest")
    if draft.scenarios:
        sources.append("teacher-selected scenarios")
    return sources
