from fastapi import APIRouter

from app.api.access_routes import router as access_router
from app.api.children_routes import router as children_router
from app.api.curriculum_routes import router as curriculum_router
from app.api.goals_routes import router as goals_router
from app.api.images_routes import router as images_router
from app.api.lessons_routes import router as lessons_router
from app.api.management_routes import router as management_router
from app.api.materials_routes import router as materials_router
from app.api.metrics_routes import router as metrics_router
from app.api.organizations_routes import router as organizations_router
from app.api.records_routes import router as records_router
from app.api.teachers_routes import router as teachers_router

router = APIRouter()

router.include_router(organizations_router)
router.include_router(teachers_router)
router.include_router(access_router)
router.include_router(curriculum_router)
router.include_router(children_router)
router.include_router(goals_router)
router.include_router(images_router)
router.include_router(lessons_router)
router.include_router(materials_router)
router.include_router(records_router)
router.include_router(management_router)
router.include_router(metrics_router)
