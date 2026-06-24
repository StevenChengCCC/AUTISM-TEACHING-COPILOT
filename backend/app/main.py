import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.domain import models as domain_models

configure_logging()
logger = logging.getLogger(__name__)
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.info("Application error on %s: %s", request.url.path, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "env": settings.ENV,
        "ai_provider": settings.AI_PROVIDER,
        "mode": "mock" if settings.AI_PROVIDER == "mock" else "external_optional",
    }

@app.get("/ready")
def readiness_check():
    return {
        "status": "ready",
        "database": "configured",
        "storage_dir": settings.STORAGE_DIR,
    }
