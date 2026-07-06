from app.core.config import Settings
from app.integrations.ai_provider import get_v2_ai_provider
from app.integrations.mock_ai_provider import MockV2AIProvider


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
