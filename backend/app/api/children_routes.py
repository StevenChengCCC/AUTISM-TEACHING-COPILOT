from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.dto import ChildProfileCreate, ChildProfileRead
from app.services.profile_service import ChildProfileService

router = APIRouter(prefix="/children", tags=["children"])


@router.post("", response_model=ChildProfileRead)
def create_child_profile(payload: ChildProfileCreate, db: Session = Depends(get_db)):
    return ChildProfileService(db).create_child_profile(payload)


@router.get("", response_model=list[ChildProfileRead])
def list_child_profiles(db: Session = Depends(get_db)):
    return ChildProfileService(db).list_child_profiles()
