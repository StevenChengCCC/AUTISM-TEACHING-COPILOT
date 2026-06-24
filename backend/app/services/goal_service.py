from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.children import ChildProfileRepository
from app.repositories.goals import TeachingGoalRepository
from app.schemas.dto import TeachingGoalCreate, TeachingGoalRead, TeachingGoalUpdate


class TeachingGoalService:
    def __init__(self, db: Session):
        self.children = ChildProfileRepository(db)
        self.goals = TeachingGoalRepository(db)

    def create_goal(self, payload: TeachingGoalCreate) -> TeachingGoalRead:
        if not self.children.get(payload.child_id):
            raise NotFoundError("Child profile not found")
        return TeachingGoalRead.model_validate(self.goals.create(payload))

    def list_goals(self, child_id: int | None = None) -> list[TeachingGoalRead]:
        if child_id is not None and not self.children.get(child_id):
            raise NotFoundError("Child profile not found")
        return [
            TeachingGoalRead.model_validate(goal) for goal in self.goals.list(child_id)
        ]

    def get_goal(self, goal_id: int) -> TeachingGoalRead:
        goal = self.goals.get(goal_id)
        if not goal:
            raise NotFoundError("Teaching goal not found")
        return TeachingGoalRead.model_validate(goal)

    def update_goal(
        self, goal_id: int, payload: TeachingGoalUpdate
    ) -> TeachingGoalRead:
        goal = self.goals.get(goal_id)
        if not goal:
            raise NotFoundError("Teaching goal not found")
        return TeachingGoalRead.model_validate(self.goals.update(goal, payload))

    def delete_goal(self, goal_id: int) -> dict:
        goal = self.goals.get(goal_id)
        if not goal:
            raise NotFoundError("Teaching goal not found")
        self.goals.delete(goal)
        return {"deleted": True, "id": goal_id}
