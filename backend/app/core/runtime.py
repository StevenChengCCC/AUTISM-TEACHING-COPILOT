from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.core.config import Settings
from app.core.exceptions import SkillConfigurationError
from app.skills.registry import get_skill_registry


CapabilityStatus = Literal["ready", "incomplete"]
RuntimeStatus = Literal["ready", "not_ready"]


@dataclass(frozen=True)
class CapabilityCheck:
    name: str
    status: CapabilityStatus
    required: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeValidationReport:
    environment: str
    status: RuntimeStatus
    production_ready: bool
    capabilities: tuple[CapabilityCheck, ...]

    @property
    def incomplete_capabilities(self) -> list[str]:
        return [
            check.name for check in self.capabilities if check.status == "incomplete"
        ]

    def to_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "status": self.status,
            "productionReady": self.production_ready,
            "capabilities": [check.to_dict() for check in self.capabilities],
        }


def _is_strict_environment(config: Settings) -> bool:
    return config.APP_ENV in {"staging", "production"}


def _cors_is_deployment_safe(config: Settings) -> bool:
    origins = config.allowed_origin_list
    return (
        bool(origins)
        and "*" not in origins
        and all(origin.startswith("https://") for origin in origins)
    )


def _ai_is_configured(config: Settings) -> bool:
    if config.AI_PROVIDER == "openai":
        return bool(config.reveal(config.OPENAI_API_KEY))
    if config.AI_PROVIDER == "azure_openai":
        has_secret_source = bool(
            config.reveal(config.AZURE_OPENAI_API_KEY) or config.KEY_VAULT_URL
        )
        return bool(
            config.AZURE_OPENAI_ENDPOINT
            and config.AZURE_OPENAI_DEPLOYMENT
            and has_secret_source
        )
    return False


def _auth_is_configured(config: Settings) -> bool:
    return bool(
        config.effective_auth_mode == "cognito"
        and config.cognito_issuer
        and config.COGNITO_APP_CLIENT_ID
        and config.COGNITO_DOMAIN
    )


def evaluate_runtime(config: Settings) -> RuntimeValidationReport:
    """Report deployment capabilities without revealing configuration values.

    Round 1 deliberately reports future capabilities instead of pretending that
    configuring an environment variable implements PostgreSQL repositories,
    Cognito authentication, or S3 storage. Staging and production remain live for
    diagnostics but are not ready for traffic until later rounds complete them.
    """

    strict = _is_strict_environment(config)
    database_persistent = not config.effective_database_url.startswith("sqlite")
    cors_safe = _cors_is_deployment_safe(config) if strict else True
    ai_configured = _ai_is_configured(config)
    ai_fail_closed = config.effective_ai_failure_mode == "fail_closed"
    auth_configured = _auth_is_configured(config)
    anonymous_disabled = (
        config.effective_auth_mode == "cognito" or not config.DEV_ALLOW_ANON_TEACHER
    )
    try:
        get_skill_registry(config).validate_required()
        skills_configured = True
    except SkillConfigurationError:
        skills_configured = False

    checks = (
        CapabilityCheck(
            name="database",
            status="ready" if database_persistent else "incomplete",
            required=strict,
            message=(
                "A non-SQLite database is configured."
                if database_persistent
                else "SQLite is local-only; staging requires PostgreSQL."
            ),
        ),
        CapabilityCheck(
            name="v2Repository",
            status=(
                "ready"
                if config.effective_v2_repository_mode == "sqlalchemy"
                and database_persistent
                else "incomplete"
            ),
            required=strict,
            message=(
                "Backend v2 uses the SQLAlchemy repository adapter."
                if config.effective_v2_repository_mode == "sqlalchemy"
                and database_persistent
                else "Backend v2 persistence requires SQLAlchemy with a non-SQLite database."
            ),
        ),
        CapabilityCheck(
            name="authentication",
            status="ready" if auth_configured else "incomplete",
            required=strict,
            message=(
                "Cognito JWT validation and request-scoped ownership are configured."
                if auth_configured
                else "Staging requires Cognito issuer, app client, and domain configuration."
            ),
        ),
        CapabilityCheck(
            name="anonymousTeacher",
            status="ready" if anonymous_disabled else "incomplete",
            required=strict,
            message=(
                "Anonymous teacher mode is disabled for the effective authentication mode."
                if anonymous_disabled
                else "Anonymous teacher mode is enabled and is local-development only."
            ),
        ),
        CapabilityCheck(
            name="cors",
            status="ready" if cors_safe else "incomplete",
            required=strict,
            message=(
                "CORS uses an explicit environment allowlist."
                if cors_safe
                else "Staging and production require explicit HTTPS origins and no wildcard."
            ),
        ),
        CapabilityCheck(
            name="objectStorage",
            status=(
                "ready"
                if config.effective_object_storage_provider == "s3"
                and bool(config.S3_BUCKET)
                else "incomplete"
            ),
            required=strict,
            message=(
                "Private S3 object storage is configured."
                if config.effective_object_storage_provider == "s3"
                and bool(config.S3_BUCKET)
                else "Staging requires a private S3 bucket; local storage is development-only."
            ),
        ),
        CapabilityCheck(
            name="aiProvider",
            status="ready" if ai_configured else "incomplete",
            required=strict,
            message=(
                "The selected external AI provider has a configured secret source."
                if ai_configured
                else "Staging requires a configured non-mock AI provider."
            ),
        ),
        CapabilityCheck(
            name="aiFailurePolicy",
            status="ready" if ai_fail_closed else "incomplete",
            required=strict,
            message=(
                "AI provider failures return a safe service error."
                if ai_fail_closed
                else "Realistic mock fallback is enabled and is local-development only."
            ),
        ),
        CapabilityCheck(
            name="skillRegistry",
            status="ready" if skills_configured else "incomplete",
            required=strict,
            message=(
                "All explicitly configured AI skill versions loaded successfully."
                if skills_configured
                else "A required explicitly configured AI skill is missing or invalid."
            ),
        ),
        CapabilityCheck(
            name="exportStorage",
            status=(
                "ready"
                if database_persistent
                and config.effective_v2_repository_mode == "sqlalchemy"
                and config.effective_object_storage_provider == "s3"
                and bool(config.S3_BUCKET)
                else "incomplete"
            ),
            required=strict,
            message=(
                "Teacher handoff metadata uses persistent storage and artifacts use private S3."
                if database_persistent
                and config.effective_v2_repository_mode == "sqlalchemy"
                and config.effective_object_storage_provider == "s3"
                and bool(config.S3_BUCKET)
                else "Staging exports require SQLAlchemy/PostgreSQL metadata and private S3 artifact storage."
            ),
        ),
    )
    deployment_required_names = {
        "database",
        "v2Repository",
        "authentication",
        "anonymousTeacher",
        "cors",
        "objectStorage",
        "aiProvider",
        "aiFailurePolicy",
        "skillRegistry",
        "exportStorage",
    }
    production_ready = all(
        check.status == "ready"
        for check in checks
        if check.name in deployment_required_names
    )
    status: RuntimeStatus = "ready" if not strict or production_ready else "not_ready"
    return RuntimeValidationReport(
        environment=config.APP_ENV,
        status=status,
        production_ready=production_ready,
        capabilities=checks,
    )
