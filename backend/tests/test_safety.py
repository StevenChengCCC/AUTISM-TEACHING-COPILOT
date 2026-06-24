import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.exceptions import SafetyDeferralError
from app.core.safety import classify_goal_safety
from app.domain.models import AuditLog, ChildProfile, ImageAsset, TeachingGoal
from app.schemas.dto import LessonPlanRequest
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
        preferred_reinforcers_json=json.dumps(["sticker"]),
        prompting_that_works="gesture prompt",
        avoid_notes="avoid long verbal instructions",
    )


@pytest.mark.parametrize(
    "target_skill",
    ["request apple", "identify apple", "imitate clapping"],
)
def test_acquisition_goals_pass(target_skill):
    verdict = classify_goal_safety(target_skill, None, None, None)

    assert verdict.requires_bcba is False
    assert verdict.category is None
    assert verdict.matched_terms == []


@pytest.mark.parametrize(
    ("target_skill", "expected_category"),
    [
        ("reduce self-injury", "self_injury"),
        ("stop hitting peers", "aggression"),
        ("decrease elopement", "elopement"),
        ("eliminate property destruction", "property_destruction"),
    ],
)
def test_reduction_goals_defer(target_skill, expected_category):
    verdict = classify_goal_safety(target_skill, None, None, None)

    assert verdict.requires_bcba is True
    assert verdict.category == expected_category
    assert verdict.matched_terms


def test_deferral_carries_category_and_matched_terms():
    verdict = classify_goal_safety(
        target_skill="eliminate behavior",
        concept="bolting",
        notes="",
        behavior_notes="",
    )

    assert verdict.requires_bcba is True
    assert verdict.category == "elopement"
    assert any("bolting" in term for term in verdict.matched_terms)


def test_create_lesson_defers_and_writes_audit_log():
    session = make_session()
    session.add(complete_child("C-SAFE"))
    session.flush()
    session.add(
        TeachingGoal(child_id=1, target_skill="reduce self-injury", concept="safety")
    )
    session.add(
        ImageAsset(
            title="Neutral image", source_type="searched", concept="safety", approved=True
        )
    )
    session.commit()

    with pytest.raises(SafetyDeferralError) as raised:
        LessonService(session).create_lesson(
            LessonPlanRequest(
                child_id=1,
                goal_id=1,
                target_skill="reduce self-injury",
                selected_image_asset_ids=[1],
            ),
            actor_teacher_id=7,
        )

    assert raised.value.payload["requires_bcba"] is True
    assert raised.value.payload["category"] == "self_injury"
    assert raised.value.payload["matched_terms"]
    assert (
        raised.value.payload["message"]
        == "This goal targets behavior reduction and must be planned by a BCBA."
    )

    audit = session.query(AuditLog).filter_by(action="safety_deferral").one()
    assert audit.actor_teacher_id == 7
    assert audit.entity_type == "TeachingGoal"
    assert audit.entity_id == 1
    assert audit.child_id == 1
    metadata = json.loads(audit.metadata_json)
    assert metadata["category"] == "self_injury"
    assert metadata["matched_terms"]
