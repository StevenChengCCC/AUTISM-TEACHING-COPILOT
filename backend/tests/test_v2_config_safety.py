import pytest

from app.core.config import Settings
from app.integrations.ai_provider import get_v2_ai_provider
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.integrations.openai_provider import OpenAIV2AIProvider
from app.schemas.v2_dto import LessonDesignDraftDto


def test_v2_defaults_to_mock_and_masks_secrets():
    settings = Settings(_env_file=None, OPENAI_API_KEY="example-not-real")

    assert settings.AI_PROVIDER == "mock"
    assert isinstance(get_v2_ai_provider(settings), MockV2AIProvider)
    assert "example-not-real" not in repr(settings)


def test_development_and_production_cors_are_environment_aware():
    development = Settings(_env_file=None, APP_ENV="development", ALLOWED_ORIGINS="")
    production = Settings(
        _env_file=None,
        APP_ENV="production",
        ALLOWED_ORIGINS="https://studio.example.org",
    )

    assert "http://localhost:5173" in development.allowed_origin_list
    assert production.allowed_origin_list == ["https://studio.example.org"]


def test_openai_defaults_and_missing_key_fail_safely_at_runtime():
    settings = Settings(_env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY=None)

    assert settings.OPENAI_TEXT_MODEL == "gpt-5.5"
    assert settings.OPENAI_IMAGE_MODEL == "gpt-image-2"
    assert settings.OPENAI_TIMEOUT_SECONDS == 60
    provider = get_v2_ai_provider(settings)
    assert isinstance(provider, OpenAIV2AIProvider)

    draft = LessonDesignDraftDto(
        id="draft-test",
        learnerId="a102",
        goalText="",
        responseLevel="",
        theme="",
        duration="",
        customNotes="",
    )
    with pytest.raises(
        RuntimeError,
        match=(
            r"OPENAI_API_KEY is not configured\. Add it to "
            r"backend/\.env\.local or your backend environment\."
        ),
    ):
        provider.generate_lesson_package(draft)


def test_local_config_searches_for_backend_env_local():
    env_files = tuple(Settings.model_config["env_file"])

    assert "backend/.env.local" in env_files
    assert ".env.local" in env_files


def test_database_defaults_to_local_sqlite():
    settings = Settings(_env_file=None)

    assert settings.effective_database_url == "sqlite:///./autism_copilot.db"


def test_explicit_database_url_takes_priority_over_rds_values():
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg2://direct-user:direct-pass@example.com:5432/directdb",
        RDS_HOSTNAME="rds.example.com",
        RDS_PORT="5432",
        RDS_DB_NAME="rdsdb",
        RDS_USERNAME="rdsuser",
        RDS_PASSWORD="fake-direct-rds-pass",
    )

    assert (
        settings.effective_database_url
        == "postgresql+psycopg2://direct-user:direct-pass@example.com:5432/directdb"
    )


def test_rds_environment_builds_postgresql_url_without_repr_secret_leak():
    settings = Settings(
        _env_file=None,
        RDS_HOSTNAME="lesson-kit-demo.abc123.us-east-1.rds.amazonaws.com",
        RDS_PORT="5432",
        RDS_DB_NAME="lessonkit",
        RDS_USERNAME="studio_user",
        RDS_PASSWORD="fake-pass-for-test",
    )

    assert (
        settings.effective_database_url
        == "postgresql+psycopg2://studio_user:fake-pass-for-test@"
        "lesson-kit-demo.abc123.us-east-1.rds.amazonaws.com:5432/lessonkit"
    )
    assert "fake-pass-for-test" not in repr(settings)


def test_incomplete_rds_environment_keeps_sqlite_default():
    settings = Settings(
        _env_file=None,
        RDS_HOSTNAME="lesson-kit-demo.abc123.us-east-1.rds.amazonaws.com",
        RDS_PORT="5432",
        RDS_DB_NAME="lessonkit",
        RDS_USERNAME="studio_user",
        RDS_PASSWORD=None,
    )

    assert settings.effective_database_url == "sqlite:///./autism_copilot.db"
