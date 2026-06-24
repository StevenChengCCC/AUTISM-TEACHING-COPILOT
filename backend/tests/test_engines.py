from app.domain.engines import (
    build_attention_segments,
    build_generalization_plan,
    build_reinforcement_plan,
    evaluate_progress,
)


def test_attention_engine_segments_short_attention_span():
    segments = build_attention_segments("request apple", 10, 5)

    assert segments[0]["type"] == "teaching"
    assert any(segment["type"] == "reinforcement" for segment in segments)
    assert sum(segment["duration_seconds"] for segment in segments) == 600


def test_generalization_engine_uses_required_dimensions():
    plan = build_generalization_plan("apple")

    dimensions = {item["dimension"] for item in plan}
    assert "visual_variation" in dimensions
    assert "physical_object_variation" in dimensions
    assert "instructor_variation" in dimensions
    assert "environment_variation" in dimensions
    assert "instruction_variation" in dimensions


def test_reinforcement_engine_builds_rotation_and_warnings():
    plan = build_reinforcement_plan(["cars"], ["sticker", "music"])

    assert plan["rotation"] == ["sticker", "music"]
    assert plan["schedule"]
    assert plan["saturation_warnings"]


def test_progress_engine_is_deterministic():
    progress = evaluate_progress(independent_count=8, prompted_count=1, error_count=1, previous_mastery_level=2)

    assert progress.mastery_level == 4
    assert progress.progress_delta == 2
    assert progress.confidence_score > 0
