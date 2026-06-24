from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressResult:
    mastery_level: int
    progress_delta: int
    confidence_score: int


GENERALIZATION_DIMENSIONS = {
    "visual_variation": ["different colors", "different sizes", "front/side/top view"],
    "physical_object_variation": [
        "real object",
        "toy version",
        "photo card",
        "simple illustration",
    ],
    "instructor_variation": ["lead teacher", "support teacher", "caregiver"],
    "environment_variation": [
        "classroom table",
        "therapy room",
        "home",
        "community setting",
    ],
    "instruction_variation": ["point to", "give me", "what is this", "find the same"],
}


def normalize_attention_span(minutes: int | None) -> int:
    if not minutes or minutes <= 0:
        return 5
    return max(2, min(minutes, 10))


def build_attention_segments(
    target_skill: str, duration_minutes: int, attention_span_minutes: int | None
) -> list[dict]:
    unit = normalize_attention_span(attention_span_minutes)
    segments: list[dict] = []
    elapsed_seconds = 0
    total_seconds = max(5, duration_minutes) * 60
    cycle = 1

    while elapsed_seconds < total_seconds:
        activity_seconds = min(
            max(120, unit * 60 - 120), total_seconds - elapsed_seconds
        )
        segments.append(
            {
                "order": len(segments) + 1,
                "type": "teaching",
                "duration_seconds": activity_seconds,
                "duration_minutes": round(activity_seconds / 60, 1),
                "title": f"Cycle {cycle}: {target_skill}",
                "activity": f"Model, prompt, and practice {target_skill} with concise instructions.",
            }
        )
        elapsed_seconds += activity_seconds
        if elapsed_seconds >= total_seconds:
            break

        reinforcement_seconds = 30 if unit <= 5 else 60
        reinforcement_seconds = min(
            reinforcement_seconds, total_seconds - elapsed_seconds
        )
        segments.append(
            {
                "order": len(segments) + 1,
                "type": "reinforcement",
                "duration_seconds": reinforcement_seconds,
                "duration_minutes": round(reinforcement_seconds / 60, 1),
                "title": "Immediate reinforcement",
                "activity": "Deliver brief reinforcement and reset attention before the next trial block.",
            }
        )
        elapsed_seconds += reinforcement_seconds
        if elapsed_seconds >= total_seconds:
            break

        break_seconds = 60 if unit <= 5 else 120
        break_seconds = min(break_seconds, total_seconds - elapsed_seconds)
        segments.append(
            {
                "order": len(segments) + 1,
                "type": "break",
                "duration_seconds": break_seconds,
                "duration_minutes": round(break_seconds / 60, 1),
                "title": "Short break",
                "activity": "Offer a predictable pause, then transition back with the same cue.",
            }
        )
        elapsed_seconds += break_seconds
        cycle += 1

    return segments


def build_generalization_plan(
    concept: str, requested_dimensions: list[str] | None = None
) -> list[dict]:
    requested = requested_dimensions or list(GENERALIZATION_DIMENSIONS)
    plan = []
    for dimension, variations in GENERALIZATION_DIMENSIONS.items():
        if dimension not in requested and dimension.replace("_", " ") not in requested:
            continue
        plan.append(
            {
                "dimension": dimension,
                "concept": concept,
                "examples": [f"{concept}: {variation}" for variation in variations],
                "status": "not_started",
            }
        )
    return plan


def build_reinforcement_plan(interests: list[str], reinforcers: list[str]) -> dict:
    rotation = (
        reinforcers
        or interests
        or ["verbal praise", "sticker", "30-second preferred activity"]
    )[:5]
    saturation_warnings = [
        f"Watch for reduced response to {item} after repeated use."
        for item in rotation[:3]
    ]
    return {
        "rotation": rotation,
        "schedule": [
            "FR1 for acquisition: reinforce each independent or close approximation.",
            "Move to VR2/VR3 after stable independent responding.",
            "Keep each reinforcement window brief so the learner can return to the task.",
        ],
        "saturation_warnings": saturation_warnings,
    }


def evaluate_progress(
    independent_count: int,
    prompted_count: int,
    error_count: int,
    previous_mastery_level: int = 0,
) -> ProgressResult:
    total = max(0, independent_count) + max(0, prompted_count) + max(0, error_count)
    if total == 0:
        return ProgressResult(
            mastery_level=0, progress_delta=-previous_mastery_level, confidence_score=0
        )

    independent_rate = independent_count / total
    success_rate = (independent_count + prompted_count * 0.5) / total
    if independent_count >= 8 and independent_rate >= 0.8:
        mastery = 4
    elif independent_rate >= 0.6:
        mastery = 3
    elif success_rate >= 0.5:
        mastery = 2
    elif independent_count + prompted_count > 0:
        mastery = 1
    else:
        mastery = 0
    confidence = round(min(100, total * 8) * max(0.2, success_rate))
    return ProgressResult(
        mastery_level=mastery,
        progress_delta=mastery - previous_mastery_level,
        confidence_score=confidence,
    )


def build_image_search_queries(
    concept: str, variations: list[str], prefer_real: bool
) -> list[str]:
    style = "photo" if prefer_real else "picture card"
    queries = []
    for variation in variations or ["general"]:
        lower = variation.lower()
        if "visual" in lower or "颜色" in variation:
            queries += [
                f"{concept} different colors {style}",
                f"{concept} different sizes {style}",
            ]
        elif "object" in lower or "媒介" in variation:
            queries += [f"{concept} real object toy photo card {style}"]
        elif "environment" in lower or "场景" in variation:
            queries += [f"{concept} classroom home community {style}"]
        else:
            queries += [f"{concept} clear isolated {style}"]
    return list(dict.fromkeys(queries))[:8]
