from fastapi import APIRouter

from app.api.children_routes import router as children_router
from app.api.goals_routes import router as goals_router
from app.api.images_routes import router as images_router
from app.api.lessons_routes import router as lessons_router
from app.api.records_routes import router as records_router

router = APIRouter()

router.include_router(children_router)
router.include_router(goals_router)
router.include_router(images_router)
router.include_router(lessons_router)
router.include_router(records_router)
