import asyncio
import json
import logging

from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import Settings, settings as app_settings
from app.core.runtime import evaluate_runtime
from app.core.exceptions import VersionConflictError
from app.main import app, app_error_handler, unhandled_error_handler


def test_runtime_mode_validation_reports_incomplete_deployment_capabilities():
    development = Settings(_env_file=None, APP_ENV="development")
    staging = Settings(
        _env_file=None,
        APP_ENV="staging",
        DATABASE_URL="postgresql+psycopg2://demo:fake@example.invalid:5432/demo",
        ALLOWED_ORIGINS="https://staging.example.org",
        DEV_ALLOW_ANON_TEACHER=False,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="fake-test-key",
        AI_FAILURE_MODE="fail_closed",
    )

    development_report = evaluate_runtime(development)
    staging_report = evaluate_runtime(staging)

    assert development_report.status == "ready"
    assert development_report.production_ready is False
    assert "aiProvider" in development_report.incomplete_capabilities
    assert staging_report.status == "not_ready"
    assert staging_report.production_ready is False
    assert {
        "authentication",
        "objectStorage",
        "exportStorage",
    }.issubset(staging_report.incomplete_capabilities)
    assert "v2Repository" not in staging_report.incomplete_capabilities


def test_unsafe_staging_configuration_is_live_but_not_ready(monkeypatch):
    monkeypatch.setattr(app_settings, "APP_ENV", "staging")
    monkeypatch.setattr(app_settings, "ALLOWED_ORIGINS", "*")
    monkeypatch.setattr(app_settings, "DEV_ALLOW_ANON_TEACHER", True)
    monkeypatch.setattr(app_settings, "AI_PROVIDER", "mock")
    monkeypatch.setattr(app_settings, "AI_FAILURE_MODE", "mock_fallback")
    monkeypatch.setattr(app_settings, "DATABASE_URL", "sqlite:///./autism_copilot.db")
    client = TestClient(app)

    live = client.get("/health/live")
    ready = client.get("/health/ready")
    ai_status = client.get("/api/v2/dev/ai-status")

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 503
    assert ai_status.status_code == 404
    assert ai_status.json()["message"] == "Not found"
    assert ready.json()["status"] == "not_ready"
    assert "database" in [
        check["name"]
        for check in ready.json()["capabilities"]
        if check["status"] == "incomplete"
    ]
    assert "DATABASE_URL" not in ready.text
    assert "OPENAI_API_KEY" not in ready.text


def test_health_endpoints_and_request_ids_are_sanitized():
    client = TestClient(app)
    supplied_request_id = "demo-request-123"

    live = client.get("/health/live", headers={"X-Request-ID": supplied_request_id})
    ready = client.get("/health/ready")
    product = client.get("/api/v2/health")

    assert live.status_code == 200
    assert live.headers["X-Request-ID"] == supplied_request_id
    assert ready.status_code == 200
    assert product.status_code == 200
    assert product.json() == {
        "status": "ok",
        "version": "v2-product",
        "environment": "development",
    }
    combined = live.text + ready.text + product.text
    assert "apiKey" not in combined
    assert "DATABASE_URL" not in combined


def test_readiness_fails_safely_when_database_probe_fails(monkeypatch):
    monkeypatch.setattr("app.main.check_database", lambda: False)
    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"]["status"] == "unavailable"
    assert "DATABASE_URL" not in response.text


def test_staging_forces_sqlalchemy_and_rejects_sqlite_readiness():
    config = Settings(
        _env_file=None,
        APP_ENV="staging",
        DATABASE_URL="sqlite:///./unsafe-staging.db",
        V2_REPOSITORY_MODE="memory",
    )

    report = evaluate_runtime(config)
    assert config.effective_v2_repository_mode == "sqlalchemy"
    assert report.status == "not_ready"
    assert {"database", "v2Repository"}.issubset(report.incomplete_capabilities)


def test_request_ids_reject_log_injection_characters():
    client = TestClient(app)
    response = client.get(
        "/health/live", headers={"X-Request-ID": "unsafe\nrequest-id"}
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "unsafe\nrequest-id"
    assert "\n" not in response.headers["X-Request-ID"]


def test_app_and_request_validation_errors_use_stable_safe_contract():
    client = TestClient(app)

    missing = client.get("/api/v2/learners/does-not-exist")
    invalid = client.post("/api/v2/learners", json={"code": "Learner T-001"})

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert missing.json()["message"] == "Learner not found"
    assert missing.json()["detail"] == "Learner not found"
    assert missing.json()["retryable"] is False
    assert missing.json()["requestId"] == missing.headers["X-Request-ID"]

    assert invalid.status_code == 422
    assert invalid.json()["code"] == "request_validation_error"
    assert invalid.json()["retryable"] is False
    assert invalid.json()["fieldErrors"]
    assert all("input" not in error for error in invalid.json()["fieldErrors"])


def test_version_conflict_uses_stable_409_contract():
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/v2/learners/a102",
            "headers": [],
            "query_string": b"",
        }
    )
    request.state.request_id = "conflict-request"
    response = asyncio.run(
        app_error_handler(
            request,
            VersionConflictError(
                "The resource changed after it was loaded. Refresh and try again."
            ),
        )
    )
    assert response.status_code == 409
    assert json.loads(response.body)["code"] == "version_conflict"
    assert json.loads(response.body)["requestId"] == "conflict-request"


def test_unhandled_error_response_does_not_expose_exception_text(caplog):
    raw_secret = "raw-student-record-and-secret-token"
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
        }
    )
    request.state.request_id = "test-unhandled"
    caplog.set_level(logging.ERROR)

    response = asyncio.run(unhandled_error_handler(request, RuntimeError(raw_secret)))
    payload = json.loads(response.body)

    assert response.status_code == 500
    assert payload["code"] == "internal_error"
    assert payload["requestId"] == "test-unhandled"
    assert raw_secret not in response.body.decode()
    assert raw_secret not in caplog.text


def test_cors_uses_explicit_development_allowlist():
    client = TestClient(app)
    preflight_headers = {
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    }

    allowed = client.options(
        "/api/v2/learners",
        headers={"Origin": "http://localhost:5173", **preflight_headers},
    )
    denied = client.options(
        "/api/v2/learners",
        headers={"Origin": "https://attacker.example", **preflight_headers},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_request_logging_excludes_student_text_and_authorization(caplog):
    client = TestClient(app)
    student_text = "UNIQUE-RAW-STUDENT-TEXT-DO-NOT-LOG"
    fake_token = "Bearer fake-secret-token-do-not-log"
    caplog.set_level(logging.INFO)

    response = client.post(
        "/api/v2/session-data",
        headers={"Authorization": fake_token},
        json={
            "learnerId": "a102",
            "lessonPackageId": "package-a102",
            "goal": "Asking for help",
            "opportunities": 0,
            "correct": 0,
            "independent": 0,
            "promptLevel": "Level 3",
            "signalsHighlighted": [],
            "teacherNotes": student_text,
        },
    )

    assert response.status_code == 422
    assert student_text not in caplog.text
    assert fake_token not in caplog.text
