from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.domain.models import ChildProfile
from app.schemas.dto import TeachingGoalCreate, TeachingGoalUpdate
from app.services.goal_service import TeachingGoalService


def make_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_goal_crud():
    session = make_session()
    session.add(ChildProfile(code="C-GOAL"))
    session.commit()

    service = TeachingGoalService(session)
    created = service.create_goal(
        TeachingGoalCreate(
            child_id=1, target_skill="request apple", concept="apple", notes="baseline"
        )
    )
    assert created.id == 1
    assert created.mastery_level == 0

    listed = service.list_goals(child_id=1)
    assert [goal.id for goal in listed] == [1]

    updated = service.update_goal(
        1, TeachingGoalUpdate(status="paused", mastery_level=2)
    )
    assert updated.status == "paused"
    assert updated.mastery_level == 2

    deleted = service.delete_goal(1)
    assert deleted == {"deleted": True, "id": 1}
    assert service.list_goals(child_id=1) == []
