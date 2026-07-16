from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.config import settings
from app.core.database import Base, check_database, engine
from app.core.exceptions import AppError, ValidationError
from app.core.logging import configure_logging, reset_request_id, set_request_id
from app.core.runtime import evaluate_runtime
from app.domain import models as domain_models
from app.models import v2_entities
from app.services.v2_repositories import repositories


configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _safe_request_id(value: str | None) -> str:
    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


def _request_id_from(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    retryable: bool,
    field_errors: list[dict[str, str]] | None = None,
    compatibility: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "requestId": _request_id_from(request),
        # Keep the existing frontend error reader compatible during migration.
        "detail": message,
    }
    if field_errors:
        payload["fieldErrors"] = field_errors
    if compatibility:
        for key, value in compatibility.items():
            if key not in payload and key != "message":
                payload[key] = value
    return payload


@asynccontextmanager
async def lifespan(_: FastAPI):
    report = evaluate_runtime(settings)
    if settings.APP_ENV in {"development", "test"}:
        # Local bootstrap remains convenient. Staging/production use Alembic only.
        Base.metadata.create_all(bind=engine)
        seed = getattr(repositories, "seed_if_empty", None)
        if callable(seed):
            seed()
        Path(settings.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    log_level = logging.INFO if report.status == "ready" else logging.WARNING
    logger.log(
        log_level,
        "runtime_validation",
        extra={
            "event": "runtime_validation",
            "environment": report.environment,
            "readiness": report.status,
            "incomplete_capabilities": report.incomplete_capabilities,
        },
    )
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Teacher-Id"],
    expose_headers=["X-Request-ID"],
)

app.include_router(router, prefix="/api")
app.mount(
    "/storage",
    StaticFiles(directory=settings.STORAGE_DIR, check_dir=False),
    name="storage",
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = _safe_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    token = set_request_id(request_id)
    started = perf_counter()
    try:
        if request.url.path.startswith(
            ("/storage/quarantine", "/storage/private-records")
        ):
            response = JSONResponse(
                status_code=404,
                content=_error_payload(
                    request,
                    code="not_found",
                    message="Not found",
                    retryable=False,
                ),
            )
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        return response
    finally:
        reset_request_id(token)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.info(
        "application_error",
        extra={
            "event": "application_error",
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )
    compatibility = exc.payload if isinstance(exc, ValidationError) else None
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request,
            code=exc.error_code,
            message=exc.message,
            retryable=exc.retryable,
            compatibility=compatibility,
        ),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
):
    field_errors = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": str(error.get("msg", "Invalid value")),
            "code": str(error.get("type", "invalid")),
        }
        for error in exc.errors()
    ]
    logger.info(
        "request_validation_error",
        extra={
            "event": "request_validation_error",
            "error_code": "request_validation_error",
            "status_code": 422,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            request,
            code="request_validation_error",
            message="The request contains invalid or missing fields.",
            retryable=False,
            field_errors=field_errors,
        ),
    )


@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    default_message = (
        HTTPStatus(exc.status_code).phrase
        if exc.status_code in HTTPStatus._value2member_map_
        else "Request failed"
    )
    message = exc.detail if isinstance(exc.detail, str) else default_message
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request,
            code=f"http_{exc.status_code}",
            message=message,
            retryable=exc.status_code >= 500,
        ),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # Exception messages and tracebacks can contain provider metadata, file paths,
    # record text, or prompts. Log only a category and correlation metadata.
    logger.error(
        "unhandled_request_error",
        extra={
            "event": "unhandled_request_error",
            "error_code": "internal_error",
            "error_category": type(exc).__name__,
            "status_code": 500,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request,
            code="internal_error",
            message="An unexpected error occurred.",
            retryable=True,
        ),
    )


def _liveness_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


@app.get("/health/live")
@app.get("/health", include_in_schema=False)
def health_check():
    return _liveness_payload()


@app.get("/health/ready")
@app.get("/ready", include_in_schema=False)
def readiness_check():
    report = evaluate_runtime(settings)
    database_ready = check_database()
    content = report.to_dict()
    content["checks"] = {
        "database": {
            "status": "ready" if database_ready else "unavailable",
            "message": (
                "Database query succeeded."
                if database_ready
                else "Database is unavailable."
            ),
        }
    }
    if not database_ready:
        content["status"] = "not_ready"
    status_code = 200 if content["status"] == "ready" else 503
    return JSONResponse(status_code=status_code, content=content)
