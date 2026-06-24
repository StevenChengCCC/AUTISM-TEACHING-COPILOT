import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.domain import models
from app.domain.models import ChildProfile
from app.schemas.dto import LessonPlanRequest, SessionRecordCreate
from app.services.lesson_service import LessonService


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_lesson_package_generation_is_rule_based():
    session = make_session()
    session.add(
        ChildProfile(
            code="C-2",
            attention_span_minutes=5,
            interests_json=json.dumps(["cars"]),
            reinforcers_json=json.dumps(["sticker"]),
        )
    )
    session.commit()

    lesson = LessonService(session).create_lesson(
        LessonPlanRequest(child_id=1, target_skill="recognize apple", duration_minutes=10)
    )

    assert lesson.ai_used is False
    assert lesson.teaching_goal["target_skill"] == "recognize apple"
    assert lesson.segments
    assert lesson.generalization_plan
    assert lesson.reinforcement_plan["rotation"] == ["sticker"]
    assert lesson.data_recording_sheet
    assert lesson.session_notes_template


def test_session_record_uses_progress_engine():
    session = make_session()
    session.add(ChildProfile(code="C-3"))
    session.commit()

    record = LessonService(session).create_record(
        SessionRecordCreate(
            child_id=1,
            target_skill="request apple",
            independent_count=8,
            prompted_count=1,
            error_count=1,
        )
    )

    assert record.mastery_level == 4
    assert record.confidence_score > 0
