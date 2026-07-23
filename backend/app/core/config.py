from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import AIProviderConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Supports running from either the repository root or backend/.
        # Real environment variables still take precedence over local files.
        env_file=(".env", "backend/.env.local", ".env.local"),
        extra="ignore",
    )

    APP_NAME: str = "Autism Teaching Copilot"
    APP_VERSION: str = "v2-product"
    APP_ENV: Literal["development", "test", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    DATABASE_URL: str = "sqlite:///./autism_copilot.db"
    TEST_DATABASE_URL: str | None = None
    V2_REPOSITORY_MODE: Literal["memory", "sqlalchemy"] = "memory"
    V2_SEED_SYNTHETIC_DATA: bool = True
    V2_DEFAULT_ORGANIZATION_ID: str = "demo-organization"
    V2_DEFAULT_USER_ID: str = "demo-teacher"
    RDS_HOSTNAME: str | None = None
    RDS_PORT: str | None = None
    RDS_DB_NAME: str | None = None
    RDS_USERNAME: str | None = None
    RDS_PASSWORD: SecretStr | None = None
    STORAGE_DIR: str = "./storage"
    ALLOWED_ORIGINS: str = "http://localhost:5173"
    DEV_ALLOW_ANON_TEACHER: bool = True
    DEV_ANON_TEACHER_ID: int = 1
    AUTH_MODE: Literal["demo", "cognito"] = "demo"
    COGNITO_REGION: str | None = None
    COGNITO_USER_POOL_ID: str | None = None
    COGNITO_APP_CLIENT_ID: str | None = None
    COGNITO_DOMAIN: str | None = None
    COGNITO_ORGANIZATION_CLAIM: str = "custom:organization_id"
    COGNITO_DEFAULT_ORGANIZATION_ID: str = "demo-organization"
    COGNITO_ADMIN_GROUP: str = "lesson-kit-admins"

    AI_PROVIDER: Literal["mock", "azure_openai", "openai"] = "mock"
    AI_FAILURE_MODE: Literal["mock_fallback", "fail_closed"] = "mock_fallback"
    SKILL_ROOT: str | None = None
    ACTIVE_LEARNER_PROFILE_SKILL_VERSION: str = "v1"
    ACTIVE_LESSON_PLANNING_SKILL_VERSION: str = "v1"
    ACTIVE_LESSON_GENERATION_SKILL_VERSION: str = "v1"
    ACTIVE_MATERIAL_GENERATION_SKILL_VERSION: str = "v1"
    ACTIVE_IMAGE_GENERATION_SKILL_VERSION: str = "v1"

    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: SecretStr | None = None
    AZURE_OPENAI_API_VERSION: str = "2025-01-01-preview"
    AZURE_OPENAI_DEPLOYMENT: str | None = None
    AZURE_OPENAI_TEXT_DEPLOYMENT: str | None = None
    AZURE_OPENAI_IMAGE_DEPLOYMENT: str | None = None

    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-5.5"  # Compatibility alias for the legacy adapter.
    OPENAI_TEXT_MODEL: str = "gpt-5.5"
    OPENAI_PROFILE_MODEL: str = "gpt-4.1-mini"
    OPENAI_PLANNING_MODEL: str = "gpt-4.1-mini"
    OPENAI_IMAGE_MODEL: str = "gpt-image-2"
    OPENAI_TIMEOUT_SECONDS: int = 60
    OPENAI_PROFILE_TIMEOUT_SECONDS: int = 45
    OPENAI_PLANNING_TIMEOUT_SECONDS: int = 45
    OPENAI_MAX_RETRIES: int = 0
    OPENAI_REASONING_EFFORT: Literal["none", "low", "medium", "high", "xhigh"] = (
        "low"
    )
    IMAGE_SEARCH_TIMEOUT_SECONDS: int = 10
    IMAGE_ASSET_STRATEGY: Literal["generate_first", "reuse_search_generate"] = (
        "generate_first"
    )

    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS: str = ".txt,.pdf,.docx"
    ALLOWED_UPLOAD_MIME_TYPES: str = (
        "text/plain,application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    UPLOAD_QUARANTINE_DIR: str = "./storage/quarantine"
    OBJECT_STORAGE_PROVIDER: Literal["local", "s3"] = "local"
    # This directory must never be placed below the publicly mounted STORAGE_DIR.
    LOCAL_PRIVATE_STORAGE_DIR: str = "./private-storage/learner-records"
    LOCAL_UPLOAD_SIGNING_SECRET: SecretStr = SecretStr(
        "development-only-upload-signing-secret"
    )
    PUBLIC_API_BASE_URL: str = "http://localhost:8000"
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_UPLOAD_PREFIX: str = "learner-records"
    S3_EXPORT_PREFIX: str = "teacher-handoff-exports"
    S3_PRESIGNED_TTL_SECONDS: int = 300
    EXPORT_DOWNLOAD_TTL_SECONDS: int = 300
    EXPORT_RETENTION_DAYS: int = 7
    MAX_EXPORT_BYTES: int = 50 * 1024 * 1024
    S3_SERVER_SIDE_ENCRYPTION: Literal["AES256", "aws:kms"] = "AES256"
    S3_KMS_KEY_ID: str | None = None
    MIN_EXTRACTED_TEXT_CHARS: int = 20
    ENABLE_UPLOAD_ANTIVIRUS_SCAN: bool = False
    MAX_UNTRUSTED_RECORD_TEXT_CHARS: int = 50_000

    PEXELS_API_KEY: SecretStr | None = None
    PIXABAY_API_KEY: SecretStr | None = None
    UNSPLASH_ACCESS_KEY: SecretStr | None = None
    KEY_VAULT_URL: str | None = None

    @property
    def allowed_origin_list(self) -> list[str]:
        configured = {
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        }
        if self.APP_ENV == "development":
            configured.update({"http://localhost:5173", "http://127.0.0.1:5173"})
        return sorted(configured)

    @property
    def cors_origin_list(self) -> list[str]:
        """Compatibility alias for the existing FastAPI bootstrap."""

        return self.allowed_origin_list

    @property
    def effective_database_url(self) -> str:
        """Resolve the database URL without exposing credentials in logs.

        Local development stays on SQLite unless DATABASE_URL is explicitly set
        to another value or Elastic Beanstalk RDS variables are present.
        """

        default_sqlite_url = "sqlite:///./autism_copilot.db"
        if self.DATABASE_URL and self.DATABASE_URL != default_sqlite_url:
            return self.DATABASE_URL

        rds_password = self.reveal(self.RDS_PASSWORD)
        if all(
            [
                self.RDS_HOSTNAME,
                self.RDS_PORT,
                self.RDS_DB_NAME,
                self.RDS_USERNAME,
                rds_password,
            ]
        ):
            username = quote_plus(self.RDS_USERNAME or "")
            password = quote_plus(rds_password or "")
            host = self.RDS_HOSTNAME
            port = self.RDS_PORT
            db_name = quote_plus(self.RDS_DB_NAME or "")
            return (
                f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{db_name}"
            )

        return self.DATABASE_URL

    @property
    def effective_v2_repository_mode(self) -> Literal["memory", "sqlalchemy"]:
        """Strict environments always use the durable adapter, never memory."""

        if self.APP_ENV in {"staging", "production"}:
            return "sqlalchemy"
        return self.V2_REPOSITORY_MODE

    @property
    def effective_auth_mode(self) -> Literal["demo", "cognito"]:
        if self.APP_ENV in {"staging", "production"}:
            return "cognito"
        return self.AUTH_MODE

    @property
    def cognito_issuer(self) -> str | None:
        if not self.COGNITO_REGION or not self.COGNITO_USER_POOL_ID:
            return None
        return (
            f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/"
            f"{self.COGNITO_USER_POOL_ID}"
        )

    @property
    def effective_object_storage_provider(self) -> Literal["local", "s3"]:
        """Strict environments never treat instance-local files as durable."""

        if self.APP_ENV in {"staging", "production"}:
            return "s3"
        return self.OBJECT_STORAGE_PROVIDER

    @property
    def effective_ai_failure_mode(self) -> Literal["mock_fallback", "fail_closed"]:
        """Never emit realistic mock content after provider failure in strict modes."""

        if self.APP_ENV in {"staging", "production"}:
            return "fail_closed"
        return self.AI_FAILURE_MODE

    @property
    def active_skill_versions(self) -> dict[str, str]:
        """Explicit mapping; active versions are never inferred from directory order."""

        return {
            "learner_profile": self.ACTIVE_LEARNER_PROFILE_SKILL_VERSION,
            "lesson_planning": self.ACTIVE_LESSON_PLANNING_SKILL_VERSION,
            "lesson_generation": self.ACTIVE_LESSON_GENERATION_SKILL_VERSION,
            "material_generation": self.ACTIVE_MATERIAL_GENERATION_SKILL_VERSION,
            "image_generation": self.ACTIVE_IMAGE_GENERATION_SKILL_VERSION,
        }

    @property
    def allowed_upload_extension_set(self) -> set[str]:
        return {
            extension.strip().lower()
            for extension in self.ALLOWED_UPLOAD_EXTENSIONS.split(",")
            if extension.strip()
        }

    @property
    def allowed_upload_mime_type_set(self) -> set[str]:
        return {
            mime.strip().lower()
            for mime in self.ALLOWED_UPLOAD_MIME_TYPES.split(",")
            if mime.strip()
        }

    @property
    def ENV(self) -> str:
        """Compatibility alias while v1 backend code is retired."""

        return self.APP_ENV

    @staticmethod
    def reveal(secret: SecretStr | None) -> str | None:
        """Reveal a secret only at the provider SDK boundary."""

        return secret.get_secret_value() if secret else None

    def require_openai_api_key(self) -> str:
        """Return the key only at a backend provider boundary, or fail safely."""

        api_key = self.reveal(self.OPENAI_API_KEY)
        if not api_key:
            raise AIProviderConfigurationError(
                "OPENAI_API_KEY is not configured. Add it to backend/.env.local or your backend environment."
            )
        return api_key

    def model_post_init(self, __context) -> None:
        if self.AZURE_OPENAI_TEXT_DEPLOYMENT and not self.AZURE_OPENAI_DEPLOYMENT:
            self.AZURE_OPENAI_DEPLOYMENT = self.AZURE_OPENAI_TEXT_DEPLOYMENT
        if self.OPENAI_TEXT_MODEL and not self.OPENAI_MODEL:
            self.OPENAI_MODEL = self.OPENAI_TEXT_MODEL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
