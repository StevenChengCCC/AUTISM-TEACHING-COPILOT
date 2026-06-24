from app.domain.engines import (
    build_attention_segments as build_lesson_segments,
    build_generalization_plan,
    build_image_search_queries,
    build_reinforcement_plan,
    evaluate_progress,
    normalize_attention_span,
)


def infer_progress_level(independent: int, prompted: int, errors: int) -> int:
    return evaluate_progress(independent, prompted, errors).mastery_level
