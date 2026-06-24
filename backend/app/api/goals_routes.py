from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dto import TeachingGoalCreate, TeachingGoalRead, TeachingGoalUpdate
from app.services.goal_service import TeachingGoalService

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=TeachingGoalRead)
def create_goal(payload: TeachingGoalCreate, db: Session = Depends(get_db)):
    return TeachingGoalService(db).create_goal(payload)


@router.get("", response_model=list[TeachingGoalRead])
def list_goals(
    child_id: int | None = Query(default=None), db: Session = Depends(get_db)
):
    return TeachingGoalService(db).list_goals(child_id)


@router.get("/{goal_id}", response_model=TeachingGoalRead)
def get_goal(goal_id: int, db: Session = Depends(get_db)):
    return TeachingGoalService(db).get_goal(goal_id)


@router.patch("/{goal_id}", response_model=TeachingGoalRead)
def update_goal(
    goal_id: int, payload: TeachingGoalUpdate, db: Session = Depends(get_db)
):
    return TeachingGoalService(db).update_goal(goal_id, payload)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    return TeachingGoalService(db).delete_goal(goal_id)
