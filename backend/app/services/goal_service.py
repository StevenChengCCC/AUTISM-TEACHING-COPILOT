from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.audit import AuditLogRepository
from app.repositories.children import ChildProfileRepository
from app.repositories.goals import TeachingGoalRepository
from app.schemas.dto import TeachingGoalCreate, TeachingGoalRead, TeachingGoalUpdate


class TeachingGoalService:
    def __init__(self, db: Session):
        self.children = ChildProfileRepository(db)
        self.goals = TeachingGoalRepository(db)

    def create_goal(
        self, payload: TeachingGoalCreate, actor_teacher_id: int | None = None
    ) -> TeachingGoalRead:
        if not self.children.get(payload.child_id):
            raise NotFoundError("Child profile not found")
        goal = self.goals.create(payload)
        AuditLogRepository(self.goals.db).write(
            actor_teacher_id, "create", "TeachingGoal", goal.id, goal.child_id
        )
        return TeachingGoalRead.model_validate(goal)

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
        self,
        goal_id: int,
        payload: TeachingGoalUpdate,
        actor_teacher_id: int | None = None,
    ) -> TeachingGoalRead:
        goal = self.goals.get(goal_id)
        if not goal:
            raise NotFoundError("Teaching goal not found")
        updated = self.goals.update(goal, payload)
        AuditLogRepository(self.goals.db).write(
            actor_teacher_id, "update", "TeachingGoal", updated.id, updated.child_id
        )
        return TeachingGoalRead.model_validate(updated)

    def delete_goal(self, goal_id: int, actor_teacher_id: int | None = None) -> dict:
        goal = self.goals.get(goal_id)
        if not goal:
            raise NotFoundError("Teaching goal not found")
        child_id = goal.child_id
        self.goals.delete(goal)
        AuditLogRepository(self.goals.db).write(
            actor_teacher_id, "delete", "TeachingGoal", goal_id, child_id
        )
        return {"deleted": True, "id": goal_id}
