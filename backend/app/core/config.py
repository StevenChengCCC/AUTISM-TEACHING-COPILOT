from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Autism Teaching Copilot"
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./autism_copilot.db"
    STORAGE_DIR: str = "./storage"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    DEV_ALLOW_ANON_TEACHER: bool = True
    DEV_ANON_TEACHER_ID: int = 1

    AI_PROVIDER: str = "mock"  # mock | azure_openai | openai

    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_API_VERSION: str = "2025-01-01-preview"
    AZURE_OPENAI_DEPLOYMENT: str | None = None
    AZURE_OPENAI_TEXT_DEPLOYMENT: str | None = None
    AZURE_OPENAI_IMAGE_DEPLOYMENT: str | None = None

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_TEXT_MODEL: str = "gpt-4.1-mini"
    OPENAI_IMAGE_MODEL: str = "gpt-image-1"

    PEXELS_API_KEY: str | None = None
    PIXABAY_API_KEY: str | None = None
    UNSPLASH_ACCESS_KEY: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    def model_post_init(self, __context) -> None:
        if self.AZURE_OPENAI_TEXT_DEPLOYMENT and not self.AZURE_OPENAI_DEPLOYMENT:
            self.AZURE_OPENAI_DEPLOYMENT = self.AZURE_OPENAI_TEXT_DEPLOYMENT
        if self.OPENAI_TEXT_MODEL and not self.OPENAI_MODEL:
            self.OPENAI_MODEL = self.OPENAI_TEXT_MODEL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
