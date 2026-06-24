from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentTeacher, get_current_teacher, require_admin
from app.core.database import get_db
from app.schemas.dto import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.services.management_service import ManagementService

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).list_organizations()


@router.post("", response_model=OrganizationRead)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).create_organization(payload, current.id)


@router.patch("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: int,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).update_organization(
        organization_id, payload, current.id
    )


@router.delete("/{organization_id}")
def delete_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current: CurrentTeacher = Depends(get_current_teacher),
):
    require_admin(db, current)
    return ManagementService(db).delete_organization(organization_id, current.id)
