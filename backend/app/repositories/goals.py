from sqlalchemy.orm import Session

from app.domain.models import TeachingGoal
from app.schemas.dto import TeachingGoalCreate, TeachingGoalUpdate


class TeachingGoalRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, goal_id: int) -> TeachingGoal | None:
        return self.db.query(TeachingGoal).filter(TeachingGoal.id == goal_id).first()

    def list(self, child_id: int | None = None) -> list[TeachingGoal]:
        query = self.db.query(TeachingGoal)
        if child_id is not None:
            query = query.filter(TeachingGoal.child_id == child_id)
        return query.order_by(TeachingGoal.id.desc()).all()

    def create(self, payload: TeachingGoalCreate) -> TeachingGoal:
        goal = TeachingGoal(
            child_id=payload.child_id,
            target_skill=payload.target_skill,
            concept=payload.concept,
            status=payload.status,
            notes=payload.notes,
        )
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def update(self, goal: TeachingGoal, payload: TeachingGoalUpdate) -> TeachingGoal:
        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(goal, key, value)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def update_mastery(self, goal: TeachingGoal, mastery_level: int) -> TeachingGoal:
        goal.mastery_level = mastery_level
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def delete(self, goal: TeachingGoal) -> None:
        self.db.delete(goal)
        self.db.commit()
