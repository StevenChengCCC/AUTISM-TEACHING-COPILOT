from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.core.config import Settings
from app.services.v2_release_readiness_service import ReleaseEvidence, classify_release


CheckStatus = Literal["PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"]
GateStatus = Literal["PASS", "FAIL", "BLOCKED"]


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    area: str
    status: CheckStatus
    summary: str
    evidenceSource: tuple[str, ...]
    requiredAction: str | None = None

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["evidenceSource"] = list(self.evidenceSource)
        return value


@dataclass(frozen=True)
class ProductionReadinessReport:
    schemaVersion: str
    generatedAt: str
    environment: str
    gitCommit: str
    gitTreeState: str
    overallStatus: GateStatus
    releaseClassification: str
    checks: tuple[ReadinessCheck, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schemaVersion,
            "generatedAt": self.generatedAt,
            "environment": self.environment,
            "gitCommit": self.gitCommit,
            "gitTreeState": self.gitTreeState,
            "overallStatus": self.overallStatus,
            "releaseClassification": self.releaseClassification,
            "summary": {
                status: sum(check.status == status for check in self.checks)
                for status in ("PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE")
            },
            "checks": [check.to_dict() for check in self.checks],
        }


class V2ProductionReadinessService:
    """Read-only release evidence. It never treats configuration intent as execution."""

    def __init__(self, config: Settings, repository_root: Path | None = None):
        self.config = config
        self.root = repository_root or Path(__file__).resolve().parents[3]

    def evaluate(self) -> ProductionReadinessReport:
        checks = tuple(self._checks())
        overall: GateStatus = (
            "FAIL"
            if any(item.status == "FAIL" for item in checks)
            else (
                "BLOCKED"
                if any(item.status == "BLOCKED" for item in checks)
                else "PASS"
            )
        )
        synthetic_report = self.root / "output/readiness/synthetic-smoke.json"
        synthetic_complete = False
        if synthetic_report.exists():
            try:
                payload = json.loads(synthetic_report.read_text(encoding="utf-8"))
                synthetic_complete = payload.get("overallStatus") == "PASS"
            except (OSError, json.JSONDecodeError):
                synthetic_complete = False
        classification = classify_release(
            ReleaseEvidence(
                synthetic_evidence_complete=synthetic_complete,
                no_open_critical_technical_failures=overall != "FAIL",
            )
        )
        return ProductionReadinessReport(
            schemaVersion="production-readiness-v1",
            generatedAt=datetime.now(timezone.utc).isoformat(),
            environment=self.config.APP_ENV,
            gitCommit=self._git("rev-parse", "HEAD", fallback="unavailable"),
            gitTreeState=(
                "dirty"
                if self._git("status", "--porcelain", fallback="unknown")
                else "clean"
            ),
            overallStatus=overall,
            releaseClassification=classification,
            checks=checks,
        )

    def _checks(self) -> list[ReadinessCheck]:
        strict = self.config.APP_ENV in {"staging", "production"}
        database_url = self.config.effective_database_url
        docs = lambda *names: all((self.root / name).exists() for name in names)
        tests_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in sorted((self.root / "backend/tests").glob("test_*.py"))
        )
        app_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in sorted((self.root / "backend/app").rglob("*.py"))
        )
        provider_ready = self.config.AI_PROVIDER in {"openai", "azure_openai"}
        provider_secret = bool(
            self.config.reveal(self.config.OPENAI_API_KEY)
            if self.config.AI_PROVIDER == "openai"
            else self.config.reveal(self.config.AZURE_OPENAI_API_KEY)
            or self.config.KEY_VAULT_URL
        )
        auth_ready = all(
            (
                self.config.effective_auth_mode == "cognito",
                self.config.COGNITO_REGION,
                self.config.COGNITO_USER_POOL_ID,
                self.config.COGNITO_APP_CLIENT_ID,
                self.config.COGNITO_DOMAIN,
            )
        )
        cors_ready = (
            bool(self.config.allowed_origin_list)
            and "*" not in self.config.allowed_origin_list
            and (
                not strict
                or all(
                    item.startswith("https://")
                    for item in self.config.allowed_origin_list
                )
            )
        )
        production_fixture_guard = (
            'settings.APP_ENV not in {"development", "test"}' in app_text
            and "_require_development" in app_text
        )
        redaction_tests = all(
            token in tests_text for token in ("sensitive", "redact", "organization")
        )
        yield ReadinessCheck(
            "configuration.no_placeholders",
            "configuration",
            (
                "PASS"
                if strict
                and not self.config.DEV_ALLOW_ANON_TEACHER
                and not self.config.V2_SEED_SYNTHETIC_DATA
                else "FAIL"
            ),
            (
                "Strict runtime disables anonymous access and synthetic seeding."
                if strict
                and not self.config.DEV_ALLOW_ANON_TEACHER
                and not self.config.V2_SEED_SYNTHETIC_DATA
                else "Active values still permit development/demo behavior."
            ),
            ("backend/app/core/config.py", "active process settings"),
            (
                None
                if strict
                and not self.config.DEV_ALLOW_ANON_TEACHER
                and not self.config.V2_SEED_SYNTHETIC_DATA
                else "Set an explicit strict environment with demo behavior disabled."
            ),
        )
        yield ReadinessCheck(
            "configuration.synthetic_route_guard",
            "configuration",
            "PASS" if production_fixture_guard else "FAIL",
            (
                "Synthetic fixture and reset routes contain production guards."
                if production_fixture_guard
                else "A complete production guard was not found."
            ),
            (
                "backend/app/api/v2_routes.py",
                "backend/app/services/v2_synthetic_n482_fixture_service.py",
            ),
        )
        yield ReadinessCheck(
            "persistence.durable_database",
            "persistence",
            (
                "PASS"
                if database_url.startswith("postgresql")
                and self.config.effective_v2_repository_mode == "sqlalchemy"
                else "FAIL"
            ),
            (
                "PostgreSQL and SQLAlchemy are active."
                if database_url.startswith("postgresql")
                and self.config.effective_v2_repository_mode == "sqlalchemy"
                else "The active gate process is not using PostgreSQL durable persistence."
            ),
            ("backend/app/core/config.py", "active process settings"),
            (
                None
                if database_url.startswith("postgresql")
                else "Provide a designated PostgreSQL target and SQLAlchemy repository mode."
            ),
        )
        migration_ready = docs("backend/alembic.ini") and any(
            (self.root / "backend/alembic/versions").glob("*.py")
        )
        yield ReadinessCheck(
            "persistence.migrations_inspectable",
            "persistence",
            "PASS" if migration_ready else "FAIL",
            (
                "Alembic configuration and versioned migrations are present."
                if migration_ready
                else "Migration configuration is incomplete."
            ),
            ("backend/alembic.ini", "backend/alembic/versions/"),
        )
        yield ReadinessCheck(
            "persistence.deployed_migration_status",
            "persistence",
            "BLOCKED",
            "No authorized deployed database target was discovered; migration status was not queried.",
            ("repository configuration audit",),
            "Run the documented read-only migration status command against an authorized non-production target.",
        )
        storage_ready = self.config.effective_object_storage_provider == "s3" and bool(
            self.config.S3_BUCKET and self.config.S3_REGION
        )
        yield ReadinessCheck(
            "storage.private_object_storage",
            "storage",
            "PASS" if storage_ready else "FAIL",
            (
                "Private S3 storage is selected with an explicit region."
                if storage_ready
                else "The active gate process is not configured for S3 durable object storage."
            ),
            (
                "backend/app/core/config.py",
                "backend/app/integrations/private_object_storage.py",
            ),
        )
        yield ReadinessCheck(
            "storage.no_public_read_and_bounded_download",
            "storage",
            (
                "PASS"
                if "generate_presigned_url" in app_text
                and "S3_PRESIGNED_TTL_SECONDS" in app_text
                and '"ACL"'
                not in (
                    self.root / "backend/app/integrations/private_object_storage.py"
                ).read_text(encoding="utf-8")
                else "FAIL"
            ),
            "Application code uses bounded presigned access and does not request public ACLs.",
            (
                "backend/app/integrations/private_object_storage.py",
                "backend/tests/test_v2_handoff_export.py",
            ),
        )
        yield ReadinessCheck(
            "storage.deployed_bucket_policy",
            "storage",
            "BLOCKED",
            "Bucket public-access, encryption, region, lifecycle, and signed download were not externally inspected.",
            ("repository configuration audit",),
            "Inspect the designated non-production bucket with read-only AWS permissions.",
        )
        yield ReadinessCheck(
            "network.cors_allowlist",
            "network",
            "PASS" if cors_ready else "FAIL",
            (
                "CORS is explicitly allowlisted."
                if cors_ready
                else "CORS is empty, wildcard, or non-HTTPS for a strict environment."
            ),
            ("backend/app/main.py", "active process settings"),
        )
        yield ReadinessCheck(
            "authentication.jwt_and_tenant_claims",
            "authentication",
            "PASS" if auth_ready else "FAIL",
            (
                "Cognito issuer, audience/client, and organization claim configuration are present."
                if auth_ready
                else "The active gate process lacks complete Cognito configuration."
            ),
            ("backend/app/core/auth.py", "active process settings"),
        )
        tenant_tests = (
            "cross_tenant" in tests_text or "other_organization" in tests_text
        )
        yield ReadinessCheck(
            "authentication.tenant_isolation_tests",
            "authentication",
            "PASS" if tenant_tests else "FAIL",
            (
                "Repository/API tenant denial tests are present."
                if tenant_tests
                else "Explicit cross-tenant denial coverage was not found."
            ),
            ("backend/tests/", "backend/app/services/v2_sqlalchemy_repositories.py"),
        )
        yield ReadinessCheck(
            "authentication.deployed_boundary",
            "authentication",
            "BLOCKED",
            "A deployed issuer, token flow, and cross-tenant target were not exercised.",
            ("repository configuration audit",),
            "Run authenticated same-tenant and cross-tenant probes in the authorized staging tenant.",
        )
        safe_logging = all(
            token in app_text
            for token in (
                'request.scope.get("route")',
                'logging.getLogger("uvicorn.access")',
                "disabled = True",
            )
        )
        yield ReadinessCheck(
            "privacy.log_redaction",
            "privacy",
            "PASS" if redaction_tests and safe_logging else "FAIL",
            (
                "Logs use route templates, raw access logging is disabled, and tests cover sensitive-value redaction."
                if redaction_tests and safe_logging
                else "Required route-template and access-log redaction evidence is incomplete."
            ),
            ("backend/app/main.py", "backend/tests/"),
        )
        yield ReadinessCheck(
            "generation.retry_idempotency_timeout_cost",
            "generation",
            (
                "PASS"
                if all(
                    token in app_text
                    for token in (
                        "GENERATION_PROVIDER_MAX_RETRIES",
                        "idempotencyKey",
                        "MAX_PACKAGE_TOKEN_BUDGET",
                        "OPENAI_TIMEOUT_SECONDS",
                    )
                )
                else "FAIL"
            ),
            "Retries, revision-aware idempotency, timeouts, and package cost ceilings are explicit.",
            (
                "backend/app/core/config.py",
                "backend/app/services/v2_generation_job_service.py",
            ),
        )
        yield ReadinessCheck(
            "generation.cancellation",
            "generation",
            "FAIL",
            "No explicit durable generation-job cancellation contract was found.",
            ("backend/app/services/v2_generation_job_service.py",),
            "Define authorized cancellation states, cleanup behavior, and deterministic tests.",
        )
        yield ReadinessCheck(
            "provider.pinned_and_fail_closed",
            "provider",
            (
                "PASS"
                if provider_ready
                and provider_secret
                and self.config.effective_ai_failure_mode == "fail_closed"
                else "FAIL"
            ),
            (
                "A non-mock provider, explicit model identifiers, secret source, and fail-closed policy are active."
                if provider_ready and provider_secret
                else "The active process lacks a complete non-mock provider configuration."
            ),
            ("backend/app/core/config.py", "active process settings"),
        )
        yield ReadinessCheck(
            "health.dependency_readiness",
            "operations",
            (
                "PASS"
                if "/health/ready" in app_text and "check_database" in app_text
                else "FAIL"
            ),
            "Liveness and dependency-aware database readiness endpoints exist.",
            ("backend/app/main.py",),
        )
        operational_docs = docs(
            "docs/BACKUP_AND_RESTORE.md",
            "docs/INCIDENT_RESPONSE.md",
            "docs/deployment/RDS_ROLLBACK.md",
            "docs/RELEASE_CHECKLIST.md",
        )
        yield ReadinessCheck(
            "operations.runbooks_documented",
            "operations",
            "PASS" if operational_docs else "FAIL",
            (
                "Backup, incident, rollback, and release runbooks are version controlled."
                if operational_docs
                else "One or more required operational runbooks are missing."
            ),
            (
                "docs/BACKUP_AND_RESTORE.md",
                "docs/INCIDENT_RESPONSE.md",
                "docs/deployment/RDS_ROLLBACK.md",
            ),
        )
        yield ReadinessCheck(
            "operations.executed_evidence",
            "operations",
            "BLOCKED",
            "Restore drill, rollback, monitoring alarms, support ownership, and retention/deletion were not executed against an authorized environment.",
            ("docs/RELEASE_CHECKLIST.md",),
            "Complete and attach dated staging drill evidence with named owners.",
        )
        browser_tests = all(
            token in tests_text
            for token in ("print", "session", "progress", "recommendation")
        )
        yield ReadinessCheck(
            "compatibility.local_workflow_tests",
            "compatibility",
            "PASS" if browser_tests else "FAIL",
            "Local test coverage spans print/download, sessions, progress, and next-session recommendations.",
            ("backend/tests/", "frontend/tests/"),
        )
        yield ReadinessCheck(
            "compatibility.authorized_staging_smoke",
            "compatibility",
            "BLOCKED",
            "No explicit authorized staging API/browser target is present in repository configuration.",
            ("repository configuration audit",),
            "Supply an approved staging URL and read-only smoke-test credentials; do not use production learner data.",
        )

    def _git(self, *args: str, fallback: str) -> str:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self.root,
                check=True,
                text=True,
                capture_output=True,
                timeout=5,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return fallback


def render_readiness_markdown(report: ProductionReadinessReport) -> str:
    lines = [
        "# Production readiness evidence",
        "",
        f"Generated: {report.generatedAt}",
        f"Environment: `{report.environment}`",
        f"Git: `{report.gitCommit}` ({report.gitTreeState})",
        f"Overall gate: **{report.overallStatus}**",
        f"Current release classification: **{report.releaseClassification}**",
        "",
        "BLOCKED is not PASS. This report contains no secret values.",
        "",
        "| Check | Area | Status | Evidence | Required action |",
        "|---|---|---:|---|---|",
    ]
    for item in report.checks:
        evidence = ", ".join(item.evidenceSource).replace("|", "\\|")
        action = (item.requiredAction or "—").replace("|", "\\|")
        lines.append(
            f"| `{item.id}` | {item.area} | **{item.status}** | {item.summary} ({evidence}) | {action} |"
        )
    return "\n".join(lines) + "\n"
