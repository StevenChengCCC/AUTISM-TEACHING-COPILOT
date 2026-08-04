from __future__ import annotations

from hashlib import sha256
import json
import re

from app.schemas.v2_dto import (
    CommunicationConstraints,
    EngagementConstraints,
    GeneralizationConstraints,
    InstructionConstraints,
    InstructionalConstraintSnapshot,
    LearnerProfile,
    LearnerRecord,
    TransitionAndBreakConstraints,
    VisualAndSensoryAccessConstraints,
)

ACTIVE_STATUSES = {
    "confirmed_current",
    "teacher_confirmed",
    "teacher_edited",
    "derived",
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _constraint_value(constraints: list[str], key: str) -> str | None:
    prefix = f"{key}="
    return next(
        (item[len(prefix) :] for item in constraints if item.startswith(prefix)), None
    )


def _constraint_int(constraints: list[str], key: str) -> int | None:
    value = _constraint_value(constraints, key)
    return int(value) if value and value.isdigit() else None


def profile_revision(learner: LearnerProfile, records: list[LearnerRecord]) -> str:
    canonical = learner.normalized_profile
    factor_payload = [
        factor.model_dump(mode="json", by_alias=True)
        for factor in (canonical.factors if canonical else [])
    ]
    record_payload = [
        {
            "id": record.id,
            "version": record.version,
            "status": record.status,
            "textHash": sha256(record.effective_text.encode("utf-8")).hexdigest(),
        }
        for record in records
        if record.status in {"ready", "reviewed"}
    ]
    content = json.dumps(
        {"age": learner.age, "factors": factor_payload, "records": record_payload},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"profile-v1-{sha256(content.encode('utf-8')).hexdigest()[:20]}"


def build_instructional_constraint_snapshot(
    learner: LearnerProfile, records: list[LearnerRecord]
) -> InstructionalConstraintSnapshot:
    factors = learner.normalized_profile.factors if learner.normalized_profile else []
    active = [
        factor
        for factor in factors
        if factor.status in ACTIVE_STATUSES
        and (
            factor.status != "derived"
            or any(
                item.startswith("derived_from_confirmed_factor=")
                for item in factor.generation_constraints
            )
        )
    ]
    constraints = [item for factor in active for item in factor.generation_constraints]

    communication_values = [f.value for f in active if f.category == "communication"]
    communication_text = " ".join(communication_values).casefold()
    accepted_modes = [
        label
        for token, label in (
            ("speech", "speech"),
            ("spoken", "speech"),
            ("aac", "AAC"),
            ("pointing", "pointing"),
            ("gesture", "gesture"),
            ("sign", "sign"),
        )
        if token in communication_text
    ]
    accepted_modes.extend(
        item.split("=", 1)[1]
        for item in constraints
        if item.startswith("accept_response_mode=")
    )
    response_options = list(learner.response_options)
    for value in (
        item.split("=", 1)[1]
        for item in constraints
        if item.startswith("response_options=")
    ):
        response_options.extend(value.split("|"))
    invalid_requirements = [
        f.value
        for f in active
        if f.category in {"communication", "prohibited_item"}
        and ("do not" in f.value.casefold() or "prohibit" in f.value.casefold())
    ]
    access = [
        f.value
        for f in active
        if f.category in {"communication", "motor_access", "language"}
    ]

    effective_supports = [
        f.value
        for f in active
        if f.category
        in {
            "receptive_language",
            "learning_strength",
            "attention",
            "prompting",
            "regulation",
        }
        and "ineffective" not in f.value.casefold()
    ]
    ineffective_supports = [
        f.value
        for f in active
        if "ineffective" in f.value.casefold()
        or any(item.startswith("avoid_") for item in f.generation_constraints)
    ]
    prompt_hierarchy = [
        f.value
        for f in active
        if f.category == "prompting" and "wait" not in f.value.casefold()
    ]
    prohibited_prompting = [
        f.value
        for f in active
        if f.category == "prohibited_item" and "prompt" in f.value.casefold()
    ]

    layout = [f.value for f in active if f.category == "visual_access"]
    sensory = [f.value for f in active if f.category == "sensory"]
    motor = [f.value for f in active if f.category == "motor_access"]
    visual_prohibited = [
        value
        for value in layout
        if "avoid" in value.casefold() or "prohibit" in value.casefold()
    ]
    audio_prohibited = [
        value
        for value in sensory
        if any(
            word in value.casefold()
            for word in ("avoid", "no ", "audio", "sound", "alarm")
        )
    ]

    current_interests = [f.value for f in active if f.category == "current_interest"]
    historical = [f.value for f in factors if f.status == "historical"]
    reinforcers = [f.value for f in active if f.category == "reinforcement"]
    not_approved = [
        f.value
        for f in factors
        if f.category == "reinforcement" and f.status == "not_approved"
    ]
    not_meaningful = [
        f.value
        for f in factors
        if f.category == "reinforcement" and f.status == "not_meaningful"
    ]

    transitions = [f.value for f in active if f.category == "transition"]
    breaks = [f.value for f in active if f.category == "regulation"]
    generalization_factors = [f for f in active if f.category == "generalization"]
    generalization_values = [f.value for f in generalization_factors]
    contexts: list[str] = []
    for factor in generalization_factors:
        if not any(
            item.startswith("minimum_generalization_contexts=")
            for item in factor.generation_constraints
        ):
            continue
        value = factor.value
        if "across " in value.casefold():
            tail = re.split(r"across\s+", value, flags=re.I, maxsplit=1)[-1]
            contexts.extend(
                part.strip(" .")
                for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", tail)
                if part.strip(" .")
            )

    excluded = [
        f.value
        for f in factors
        if f.status in {"not_approved", "not_meaningful", "rejected"}
        or f.category == "prohibited_item"
    ]
    unresolved = [f.value for f in factors if f.status == "unconfirmed"]
    safety = [f.value for f in active if f.category in {"safety", "prohibited_item"}]

    return InstructionalConstraintSnapshot(
        learnerId=learner.id,
        profileRevision=profile_revision(learner, records),
        communication=CommunicationConstraints(
            acceptedModes=_unique(accepted_modes),
            responseOptions=_unique(response_options),
            processingTimeSeconds=_constraint_int(
                constraints, "minimum_processing_wait_seconds"
            ),
            accessRequirements=_unique(access),
            invalidRequirements=_unique(invalid_requirements),
        ),
        instruction=InstructionConstraints(
            effectiveSupports=_unique(effective_supports),
            ineffectiveSupports=_unique(ineffective_supports),
            promptHierarchy=_unique(prompt_hierarchy),
            prohibitedPrompting=_unique(prohibited_prompting),
            errorCorrection=_unique(
                [f.value for f in active if f.category == "error_correction"]
            ),
            activityDurationMinutes=_constraint_int(
                constraints, "maximum_teaching_block_minutes"
            ),
            visibleEndpointRequired=any(
                "visible endpoint" in f.value.casefold() for f in active
            ),
        ),
        visualAndSensoryAccess=VisualAndSensoryAccessConstraints(
            maximumPrimaryChoices=_constraint_int(
                constraints, "maximum_response_options_per_page"
            ),
            layoutRequirements=_unique(layout),
            preferredOrganizingFeatures=_unique(
                [
                    value
                    for value in layout
                    if "accent" in value.casefold() or "organizing" in value.casefold()
                ]
            ),
            prohibitedVisualFeatures=_unique(visual_prohibited),
            prohibitedAudioFeatures=_unique(audio_prohibited),
            motorAccessAlternatives=_unique(motor),
        ),
        engagement=EngagementConstraints(
            currentInterests=_unique(current_interests),
            historicalInterests=_unique(historical),
            effectiveReinforcers=_unique(reinforcers),
            notApprovedReinforcers=_unique(not_approved),
            notMeaningfulReinforcers=_unique(not_meaningful),
        ),
        transitionsAndBreaks=TransitionAndBreakConstraints(
            difficultTransitions=_unique(
                [value for value in transitions if "difficult" in value.casefold()]
            ),
            transitionWarnings=_unique(
                [value for value in transitions if "warning" in value.casefold()]
            ),
            firstThenRequired=any(
                "first–then" in value.casefold() or "first-then" in value.casefold()
                for value in transitions
            ),
            breakRequestOptions=_unique(breaks),
            breakDurationMinutes=next(
                (
                    int(match.group(1))
                    for value in breaks
                    if (match := re.search(r"(\d+)\s*-?minute", value))
                ),
                _constraint_int(constraints, "break_duration_minutes"),
            ),
            returnSupports=_unique(
                [value for value in transitions if "return" in value.casefold()]
            ),
        ),
        generalization=GeneralizationConstraints(
            required=bool(generalization_values), contexts=_unique(contexts)
        ),
        safetyConstraints=_unique(safety),
        unresolvedAssumptions=_unique(unresolved),
        excludedItems=_unique(excluded),
        profileFactorIds=[f.id for f in factors if f.status != "omitted"],
    )
