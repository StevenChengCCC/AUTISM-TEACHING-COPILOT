import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.exceptions import ValidationError
from app.domain import models
from app.domain.models import ChildProfile, ImageAsset, TeachingGoal
from app.schemas.dto import LessonPlanRequest, SessionRecordCreate
from app.services.lesson_service import LessonService


def make_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def complete_child(code: str) -> ChildProfile:
    return ChildProfile(
        code=code,
        attention_span_minutes=5,
        communication_mode="short spoken phrases",
        current_level="matches identical picture cards",
        interests_json=json.dumps(["cars"]),
        reinforcers_json=json.dumps(["sticker"]),
        preferred_reinforcers_json=json.dumps(["sticker"]),
        prompting_that_works="gesture prompt",
        avoid_notes="avoid long verbal instructions",
    )


def test_lesson_package_generation_is_rule_based():
    session = make_session()
    session.add(complete_child("C-2"))
    session.flush()
    session.add(
        TeachingGoal(child_id=1, target_skill="recognize apple", concept="apple")
    )
    session.add(
        ImageAsset(
            title="Apple photo", source_type="searched", concept="apple", approved=True
        )
    )
    session.commit()

    lesson = LessonService(session).create_lesson(
        LessonPlanRequest(
            child_id=1,
            goal_id=1,
            target_skill="recognize apple",
            duration_minutes=10,
            print_formats=["a4", "letter"],
            selected_image_asset_ids=[1],
        )
    )

    assert lesson.ai_used is False
    assert lesson.goal_id == 1
    assert lesson.teaching_goal["target_skill"] == "recognize apple"
    assert lesson.segments
    assert lesson.generalization_plan
    assert lesson.reinforcement_plan["rotation"] == ["sticker"]
    assert lesson.data_recording_sheet
    assert lesson.session_notes_template
    assert set(lesson.downloadable_card_pdf_links) == {"a4", "letter"}


def test_lesson_generation_returns_guided_questions_for_incomplete_profile():
    session = make_session()
    session.add(ChildProfile(code="C-INCOMPLETE"))
    session.flush()
    session.add(
        TeachingGoal(child_id=1, target_skill="recognize apple", concept="apple")
    )
    session.add(
        ImageAsset(
            title="Apple photo", source_type="searched", concept="apple", approved=True
        )
    )
    session.commit()

    try:
        LessonService(session).create_lesson(
            LessonPlanRequest(
                child_id=1,
                goal_id=1,
                target_skill="recognize apple",
                selected_image_asset_ids=[1],
            )
        )
    except ValidationError as exc:
        completeness = exc.payload["profile_completeness"]
        assert completeness["is_complete"] is False
        assert "attention_span_minutes" in completeness["missing_fields"]
        assert completeness["guided_questions"]
    else:
        raise AssertionError("Expected incomplete profile to block generation")


def test_session_record_uses_progress_engine():
    session = make_session()
    session.add(complete_child("C-3"))
    session.flush()
    session.add(TeachingGoal(child_id=1, target_skill="request apple", concept="apple"))
    session.commit()

    record = LessonService(session).create_record(
        SessionRecordCreate(
            child_id=1,
            goal_id=1,
            target_skill="request apple",
            independent_count=8,
            prompted_count=1,
            error_count=1,
        )
    )

    assert record.mastery_level == 4
    assert record.confidence_score > 0
    assert session.get(TeachingGoal, 1).mastery_level == 4
