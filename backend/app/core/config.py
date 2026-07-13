from functools import lru_cache
from typing import Literal

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
    APP_ENV: Literal["development", "test", "staging", "production"] = "development"
    DATABASE_URL: str = "sqlite:///./autism_copilot.db"
    STORAGE_DIR: str = "./storage"
    ALLOWED_ORIGINS: str = "http://localhost:5173"
    DEV_ALLOW_ANON_TEACHER: bool = True
    DEV_ANON_TEACHER_ID: int = 1

    AI_PROVIDER: Literal["mock", "azure_openai", "openai"] = "mock"

    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: SecretStr | None = None
    AZURE_OPENAI_API_VERSION: str = "2025-01-01-preview"
    AZURE_OPENAI_DEPLOYMENT: str | None = None
    AZURE_OPENAI_TEXT_DEPLOYMENT: str | None = None
    AZURE_OPENAI_IMAGE_DEPLOYMENT: str | None = None

    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-5.5"  # Compatibility alias for the legacy adapter.
    OPENAI_TEXT_MODEL: str = "gpt-5.5"
    OPENAI_IMAGE_MODEL: str = "gpt-image-2"
    OPENAI_TIMEOUT_SECONDS: int = 60
    IMAGE_SEARCH_TIMEOUT_SECONDS: int = 10
    IMAGE_ASSET_STRATEGY: Literal[
        "generate_first", "reuse_search_generate"
    ] = "generate_first"

    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS: str = ".txt,.pdf,.docx,.png,.jpg,.jpeg"
    ALLOWED_UPLOAD_MIME_TYPES: str = (
        "text/plain,application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "image/png,image/jpeg"
    )
    UPLOAD_QUARANTINE_DIR: str = "./storage/quarantine"
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
