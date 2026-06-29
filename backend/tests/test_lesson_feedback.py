import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.models import AuditLog, ChildProfile, ImageAsset, TeachingGoal
from app.schemas.dto import (
    ArtifactFeedbackItem,
    ArtifactFeedbackSubmit,
    LessonPlanRequest,
)
from app.services.feedback_service import LessonFeedbackService
from app.services.lesson_service import LessonService

FIXTURE_PNG = Path(__file__).parent / "fixtures" / "sample_card.png"


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


def _setup_lesson(session):
    session.add(complete_child("C-FB"))
    session.flush()
    session.add(
        TeachingGoal(child_id=1, target_skill="recognize apple", concept="apple")
    )
    session.add(
        ImageAsset(
            title="Apple photo",
            source_type="searched",
            concept="apple",
            approved=True,
            local_path=str(FIXTURE_PNG),
        )
    )
    session.commit()
    return LessonService(session).create_lesson(
        LessonPlanRequest(
            child_id=1,
            goal_id=1,
            target_skill="recognize apple",
            duration_minutes=10,
            selected_image_asset_ids=[1],
        )
    )


def test_direct_use_rate_end_to_end():
    session = make_session()
    lesson = _setup_lesson(session)

    service = LessonFeedbackService(session)
    service.submit_feedback(
        lesson.id,
        ArtifactFeedbackSubmit(
            items=[
                ArtifactFeedbackItem(
                    artifact_type="teacher_script", disposition="used_as_is"
                ),
                ArtifactFeedbackItem(
                    artifact_type="generalization_plan", disposition="used_as_is"
                ),
                ArtifactFeedbackItem(
                    artifact_type="reinforcement_plan", disposition="used_as_is"
                ),
                ArtifactFeedbackItem(
                    artifact_type="data_recording_sheet", disposition="used_as_is"
                ),
                ArtifactFeedbackItem(
                    artifact_type="session_notes_template",
                    disposition="edited",
                    edit_note="reworded one section",
                ),
            ]
        ),
        actor_teacher_id=1,
    )

    metrics = service.direct_use_metrics()
    assert metrics.total_rated == 5
    assert metrics.direct_use_rate == 0.8
    assert metrics.by_disposition.used_as_is == 4
    assert metrics.by_disposition.edited == 1
    assert metrics.by_artifact_type["session_notes_template"].edited == 1
    assert metrics.by_artifact_type["teacher_script"].used_as_is == 1

    # Audit row written for the submission.
    assert (
        session.query(AuditLog)
        .filter(AuditLog.entity_type == "LessonArtifactFeedback")
        .count()
        == 1
    )

    # Read-back of this lesson's feedback returns all five rows.
    assert len(service.list_feedback(lesson.id)) == 5


def test_metrics_filter_by_child_and_empty_is_zero():
    session = make_session()
    lesson = _setup_lesson(session)
    service = LessonFeedbackService(session)

    # No feedback yet -> zero rate, no division error.
    empty = service.direct_use_metrics()
    assert empty.total_rated == 0
    assert empty.direct_use_rate == 0.0

    service.submit_feedback(
        lesson.id,
        ArtifactFeedbackSubmit(
            items=[
                ArtifactFeedbackItem(
                    artifact_type="teacher_script", disposition="used_as_is"
                )
            ]
        ),
        actor_teacher_id=1,
    )
    assert service.direct_use_metrics(child_id=1).total_rated == 1
    assert service.direct_use_metrics(child_id=999).total_rated == 0


def test_invalid_artifact_and_disposition_rejected():
    session = make_session()
    lesson = _setup_lesson(session)
    service = LessonFeedbackService(session)

    for bad in (
        ArtifactFeedbackItem(artifact_type="bogus", disposition="used_as_is"),
        ArtifactFeedbackItem(artifact_type="teacher_script", disposition="bogus"),
    ):
        try:
            service.submit_feedback(
                lesson.id, ArtifactFeedbackSubmit(items=[bad]), actor_teacher_id=1
            )
        except ValidationError:
            pass
        else:
            raise AssertionError("Expected ValidationError for invalid feedback")


def test_feedback_for_missing_lesson_raises():
    session = make_session()
    service = LessonFeedbackService(session)
    try:
        service.submit_feedback(
            123,
            ArtifactFeedbackSubmit(
                items=[
                    ArtifactFeedbackItem(
                        artifact_type="teacher_script", disposition="used_as_is"
                    )
                ]
            ),
        )
    except NotFoundError:
        pass
    else:
        raise AssertionError("Expected NotFoundError for missing lesson")
