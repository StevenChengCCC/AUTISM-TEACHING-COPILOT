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
    factors = learner.normalized_profile.factors if learner.normalized_profile else []
    current_factors = [
        factor for factor in factors if factor.status == "confirmed_current"
    ]
    excluded_factors = [
        factor
        for factor in factors
        if factor.status in {"not_approved", "not_meaningful"}
    ]
    factor_interests = [
        factor.value
        for factor in current_factors
        if factor.category == "current_interest"
    ]
    factor_reinforcers = [
        factor.value for factor in current_factors if factor.category == "reinforcement"
    ]
    interests = factor_interests or (
        learner.interests if reviewed else _signal_labels(learner, "interest")
    )
    reinforcers = factor_reinforcers or (
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
        "profileFactors": [
            {
                "category": factor.category,
                "label": factor.label,
                "value": factor.value,
                "status": factor.status,
                "instructionalImplication": factor.instructional_implication,
                "generationConstraints": factor.generation_constraints,
            }
            for factor in [*current_factors, *excluded_factors]
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
    """Build an instructional-asset prompt from minimized context.

    Printable reference cards should depict the concept itself.  A common image
    model failure is to turn an object-identification target into a scene of an
    adult teaching a child.  That scene is decorative, but it cannot be used as
    the child's reference card.  Object-first materials therefore explicitly
    prohibit people, hands, classrooms, and demonstrations.
    """

    context = build_image_generation_context(learner, material_type, concept)

    safe_concept = context["concept"] or "a common classroom activity"
    theme = context["interestTheme"]
    if theme:
        theme_clause = (
            f"A subtle {theme} interest may influence accent colors only when it "
            "does not change or obscure the target concept."
        )
    else:
        theme_clause = (
            "Use neutral classroom materials such as blocks, pencils, or books."
        )
    cleaned_provider_prompt = _remove_direct_identifiers(learner, provider_prompt)
    object_first_types = {
        "quantity_cards",
        "number_cards",
        "visual_card",
        "matching_page",
        "sorting_page",
        "token_board",
    }
    child_action_types = {
        "help_card",
        "break_card",
        "scenario_cards",
        "sequence_cards",
        "social_narrative",
        "visual_schedule",
        "task_analysis_cards",
    }
    # Object reference cards and universal communication symbols must be driven
    # by the current server-authored concept. Appending a provider prompt here
    # can reintroduce a stale concept from an earlier teacher request.
    ignore_provider_direction = object_first_types | {
        "help_card",
        "break_card",
        "teacher_cue_card",
    }
    optional_direction = (
        f" Provider direction: {cleaned_provider_prompt}"
        if cleaned_provider_prompt and material_type not in ignore_provider_direction
        else ""
    )
    if material_type in object_first_types:
        composition = (
            f"Create exactly one clean teaching reference image of {safe_concept}. "
            "Show the target object or symbol itself, centered and large, occupying "
            "most of the canvas. Do not show a teacher, therapist, parent, child, "
            "hand, pointing gesture, classroom, lesson, demonstration, worksheet, "
            "card frame, border, caption, or surrounding scene. "
        )
    elif material_type in child_action_types:
        composition = (
            f"Create one clear teaching image of {safe_concept}. If a person is "
            "essential to the concept, show one fictional child performing the "
            "target action without an adult, teacher, therapist, audience, or "
            "classroom demonstration. Keep the action unambiguous. "
        )
    else:
        composition = (
            f"Create one clean printable educational image of {safe_concept}. "
            "Use one clear focal subject and no teaching demonstration. "
        )
    prompt = (
        composition
        + f"{theme_clause} Use a plain white or transparent-looking background, "
        "bold friendly shapes, high contrast, age-respectful styling, and consistent "
        "lighting. Do not include names, learner codes, diagnoses, logos, branded "
        "characters, record text, embedded text, watermarks, or decorative borders. "
        "The image will be placed directly into a teacher-reviewed printable PDF."
        f"{optional_direction}"
    )
    alt_text = f"Teacher-reviewable instructional image of {safe_concept}."
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
