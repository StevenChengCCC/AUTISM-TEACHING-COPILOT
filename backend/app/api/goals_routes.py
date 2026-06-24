from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_child_access
from app.core.database import get_db
from app.schemas.dto import TeachingGoalCreate, TeachingGoalRead, TeachingGoalUpdate
from app.services.goal_service import TeachingGoalService

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=TeachingGoalRead)
def create_goal(
    payload: TeachingGoalCreate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_child_access(db, payload.child_id, current, "editor")
    return TeachingGoalService(db).create_goal(payload, current.id)


@router.get("", response_model=list[TeachingGoalRead])
def list_goals(
    child_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    if child_id is not None:
        require_child_access(db, child_id, current, "viewer")
    return TeachingGoalService(db).list_goals(child_id)


@router.get("/{goal_id}", response_model=TeachingGoalRead)
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    goal = TeachingGoalService(db).get_goal(goal_id)
    require_child_access(db, goal.child_id, current, "viewer")
    return goal


@router.patch("/{goal_id}", response_model=TeachingGoalRead)
def update_goal(
    goal_id: int,
    payload: TeachingGoalUpdate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    goal = TeachingGoalService(db).get_goal(goal_id)
    require_child_access(db, goal.child_id, current, "editor")
    return TeachingGoalService(db).update_goal(goal_id, payload, current.id)


@router.delete("/{goal_id}")
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    goal = TeachingGoalService(db).get_goal(goal_id)
    require_child_access(db, goal.child_id, current, "editor")
    return TeachingGoalService(db).delete_goal(goal_id, current.id)
