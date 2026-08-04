from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging import configure_logging
from app.main import _privacy_safe_route_path
from app.services.v2_browser_smoke_report import validate_browser_smoke_report
from app.services.v2_production_readiness_service import (
    V2ProductionReadinessService,
    render_readiness_markdown,
)
from app.services.v2_release_readiness_service import (
    ReleaseEvidence,
    StudyThresholds,
    classify_release,
)
from app.services.v2_synthetic_smoke_service import V2SyntheticSmokeService
from app.services.v2_usability_telemetry_service import (
    UsabilityEvent,
    V2UsabilityTelemetryService,
)


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _event(**changes):
    payload = dict(
        schemaVersion="usability-event-v1",
        eventId="event-1",
        participantId="P-001",
        syntheticCaseId="SYN-N482-E2E",
        eventName="task_completed",
        taskName="record_valid_trial",
        occurredAt="2026-08-04T08:00:00Z",
        durationMs=12000,
        interactionCount=3,
        rating=4,
        outcome="success",
        errorCategory=None,
    )
    payload.update(changes)
    return UsabilityEvent(**payload)


def test_production_gate_fails_closed_and_never_exposes_secrets():
    secret = "super-secret-readiness-value"
    config = Settings(
        APP_ENV="production",
        DEV_ALLOW_ANON_TEACHER=True,
        V2_SEED_SYNTHETIC_DATA=True,
        OPENAI_API_KEY=SecretStr(secret),
    )
    report = V2ProductionReadinessService(config, ROOT).evaluate()
    payload = json.dumps(report.to_dict())
    assert report.overallStatus == "FAIL"
    assert report.releaseClassification in {"Not ready", "Demo ready"}
    assert secret not in payload
    assert any(item.status == "BLOCKED" for item in report.checks)
    assert any(
        item.id == "generation.cancellation" and item.status == "FAIL"
        for item in report.checks
    )


def test_gate_order_and_markdown_are_reproducible_after_volatile_fields_are_removed():
    config = Settings(APP_ENV="production")
    one = V2ProductionReadinessService(config, ROOT).evaluate()
    two = V2ProductionReadinessService(config, ROOT).evaluate()
    assert [item.id for item in one.checks] == [item.id for item in two.checks]
    assert len({item.id for item in one.checks}) == len(one.checks)
    rendered = render_readiness_markdown(one)
    assert "BLOCKED is not PASS" in rendered
    assert "| Check | Area | Status |" in rendered


def test_release_classification_requires_executed_evidence_not_documents():
    assert classify_release(ReleaseEvidence()) == "Not ready"
    assert (
        classify_release(ReleaseEvidence(synthetic_evidence_complete=True))
        == "Demo ready"
    )
    controlled = ReleaseEvidence(
        synthetic_evidence_complete=True,
        no_open_critical_technical_failures=True,
        privacy_security_review_complete=True,
        authorized_nonproduction_smoke_complete=True,
        physical_printer_evidence_complete=True,
        teacher_study_participants=3,
        teacher_study_thresholds_met=True,
    )
    assert classify_release(controlled) == "Controlled pilot ready"
    assert (
        classify_release(
            ReleaseEvidence(
                **{
                    **controlled.__dict__,
                    "production_auth_tenant_storage_download_verified": True,
                    "backup_restore_and_rollback_verified": True,
                    "monitoring_and_support_ownership_verified": True,
                    "retention_and_deletion_verified": True,
                    "high_findings_closed_or_accepted": True,
                }
            )
        )
        == "Pilot ready"
    )


def test_study_thresholds_are_versioned_and_frozen_before_results():
    thresholds = StudyThresholds()
    assert thresholds.version == "teacher-usability-v1"
    assert thresholds.minimum_overall_task_completion_percent == 90
    assert thresholds.minimum_critical_task_completion_percent == 100
    with pytest.raises(Exception):
        thresholds.maximum_critical_issues = 1


def test_usability_telemetry_is_disabled_without_explicit_opt_in_and_in_production():
    sink: list[dict[str, object]] = []
    dev = V2UsabilityTelemetryService(
        Settings(
            APP_ENV="test",
            USABILITY_TELEMETRY_ENABLED=True,
            USABILITY_TELEMETRY_SINK="memory",
        ),
        sink,
    )
    with pytest.raises(PermissionError):
        dev.record(_event(), opted_in=False)
    assert dev.record(_event(), opted_in=True)["participantId"] == "P-001"
    assert len(sink) == 1
    prod = V2UsabilityTelemetryService(
        Settings(
            APP_ENV="production",
            USABILITY_TELEMETRY_ENABLED=True,
            USABILITY_TELEMETRY_SINK="memory",
        )
    )
    assert prod.status()["enabled"] is False
    with pytest.raises(RuntimeError):
        prod.record(_event(), opted_in=True)


@pytest.mark.parametrize(
    "changes",
    [
        {"participantId": "Learner N-482"},
        {"syntheticCaseId": "REAL-001"},
        {"errorCategory": "record text"},
        {"rating": 6},
        {"durationMs": 9_000_000},
    ],
)
def test_telemetry_schema_rejects_identifiers_content_and_out_of_range_values(changes):
    with pytest.raises(ValueError):
        _event(**changes).validate()


def test_telemetry_export_delete_and_retention_are_participant_scoped():
    sink: list[dict[str, object]] = []
    service = V2UsabilityTelemetryService(
        Settings(
            APP_ENV="test",
            USABILITY_TELEMETRY_ENABLED=True,
            USABILITY_TELEMETRY_SINK="memory",
            USABILITY_TELEMETRY_RETENTION_DAYS=30,
        ),
        sink,
    )
    service.record(_event(), opted_in=True)
    service.record(
        _event(eventId="old", participantId="P-002", occurredAt="2026-01-01T00:00:00Z"),
        opted_in=True,
    )
    assert len(service.export_participant("P-001")) == 1
    assert service.purge_expired(datetime(2026, 8, 4, tzinfo=timezone.utc)) == 1
    assert service.delete_participant("P-001") == 1
    assert sink == []


def test_synthetic_corpus_has_required_coverage_and_no_privacy_sentinels():
    service = V2SyntheticSmokeService(BACKEND)
    cases = service.load_cases()
    assert len(cases) >= 12
    stages = {item["stage"] for item in cases}
    assert {
        "end_to_end",
        "authorization",
        "generation_job",
        "pdf_composition",
        "session_recording",
        "next_session",
    } <= stages
    raw = service.corpus_path.read_text(encoding="utf-8").casefold()
    for sentinel in ("@gmail.com", "social security", "date of birth", "api_key"):
        assert sentinel not in raw


def test_browser_smoke_schema_labels_system_timing_and_rejects_urls():
    payload = {
        "schemaVersion": "browser-smoke-v1",
        "timingKind": "system_automation_not_teacher_time",
        "tasks": [
            {
                "taskId": "reset_fixture",
                "status": "PASS",
                "systemDurationMs": 250,
                "interactionCount": 1,
                "unexpectedDetours": 0,
                "consoleErrors": 0,
                "networkErrors": 0,
                "evidence": "Synthetic fixture banner and learner list visible",
            }
        ],
    }
    validate_browser_smoke_report(payload)
    payload["tasks"][0]["evidence"] = "http://localhost/private"
    with pytest.raises(ValueError):
        validate_browser_smoke_report(payload)


def test_request_logging_uses_route_templates_and_disables_raw_access_log():
    class Route:
        path = "/api/v2/exports/local/{token}"

    class URL:
        path = "/api/v2/exports/local/signed-secret-token"

    class Request:
        scope = {"route": Route()}
        url = URL()

    assert _privacy_safe_route_path(Request()) == "/api/v2/exports/local/{token}"
    configure_logging("INFO")
    import logging

    assert logging.getLogger("uvicorn.access").disabled is True
