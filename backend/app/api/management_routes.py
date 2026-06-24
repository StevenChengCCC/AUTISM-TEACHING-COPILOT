from fastapi import APIRouter

from app.services.management_placeholder_service import ManagementPlaceholderService

router = APIRouter(prefix="/management", tags=["management"])


@router.get("/capabilities")
def management_capabilities():
    return ManagementPlaceholderService().capabilities()
