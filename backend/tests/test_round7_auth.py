from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import auth as auth_module
from app.core.auth import OIDCJWTValidator
from app.core.auth_context import AuthenticatedScope, reset_authenticated_scope, set_authenticated_scope
from app.core.config import Settings
from app.core.database import Base
from app.core.exceptions import AuthenticationError, SessionExpiredError
from app.main import app
from app.models import v2_entities  # noqa: F401 - register durable tables
from app.schemas.v2_dto import LearnerProfile
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories


class _SigningKey:
    def __init__(self, key):
        self.key = key


class _JwksClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token: str):
        return _SigningKey(self.key)


def _config() -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV="test",
        AUTH_MODE="cognito",
        COGNITO_REGION="us-east-1",
        COGNITO_USER_POOL_ID="us-east-1_synthetic",
        COGNITO_APP_CLIENT_ID="public-browser-client",
        COGNITO_DOMAIN="https://synthetic.auth.us-east-1.amazoncognito.com",
    )


def _token(config: Settings, private_key, **updates) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "synthetic-teacher-subject",
        "iss": config.cognito_issuer,
        "aud": config.COGNITO_APP_CLIENT_ID,
        "token_use": "id",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    claims.update(updates)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


def test_cognito_validator_checks_signature_issuer_audience_and_expiration():
    config = _config()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    validator = OIDCJWTValidator(config, _JwksClient(private_key.public_key()))

    claims = validator.validate(_token(config, private_key))
    assert claims["sub"] == "synthetic-teacher-subject"

    with pytest.raises(AuthenticationError):
        validator.validate(_token(config, private_key, aud="another-client"))
    with pytest.raises(AuthenticationError):
        validator.validate(_token(config, private_key, iss="https://invalid.example"))
    with pytest.raises(SessionExpiredError):
        validator.validate(
            _token(
                config,
                private_key,
                exp=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        )


def test_v2_requires_authentication_in_strict_mode_but_health_stays_public(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "APP_ENV", "staging")
    monkeypatch.setattr(auth_module.settings, "AUTH_MODE", "cognito")
    monkeypatch.setattr(auth_module.settings, "COGNITO_REGION", "us-east-1")
    monkeypatch.setattr(
        auth_module.settings, "COGNITO_USER_POOL_ID", "us-east-1_synthetic"
    )
    monkeypatch.setattr(
        auth_module.settings, "COGNITO_APP_CLIENT_ID", "public-browser-client"
    )
    client = TestClient(app)

    assert client.get("/api/v2/health").status_code == 200
    response = client.get("/api/v2/learners")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert response.json()["requestId"]


def test_authenticated_identity_and_organization_come_from_verified_claims(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "APP_ENV", "development")
    monkeypatch.setattr(auth_module.settings, "AUTH_MODE", "cognito")
    monkeypatch.setattr(auth_module.settings, "COGNITO_REGION", "us-east-1")
    monkeypatch.setattr(
        auth_module.settings, "COGNITO_USER_POOL_ID", "us-east-1_synthetic"
    )
    monkeypatch.setattr(
        auth_module.settings, "COGNITO_APP_CLIENT_ID", "public-browser-client"
    )

    class _Validator:
        def validate(self, _token: str):
            return {
                "sub": "teacher-verified",
                "exp": 2_000_000_000,
                "email": "teacher@example.test",
                "name": "Synthetic Teacher",
                "custom:organization_id": "verified-organization",
                "cognito:groups": ["lesson-kit-admins"],
            }

    monkeypatch.setattr(auth_module, "get_oidc_validator", lambda: _Validator())
    response = TestClient(app).get(
        "/api/v2/auth/me", headers={"Authorization": "Bearer synthetic.jwt.value"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "subject": "teacher-verified",
        "displayName": "Synthetic Teacher",
        "email": "teacher@example.test",
        "organizationId": "verified-organization",
        "role": "admin",
        "expiresAt": 2_000_000_000,
        "authenticationMode": "cognito",
    }


def test_verified_request_scope_overrides_repository_defaults(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'round7.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    repository = SQLAlchemyV2Repositories(
        factory,
        Settings(_env_file=None, APP_ENV="test", V2_SEED_SYNTHETIC_DATA=False),
        organization_external_id="default-org",
        user_external_id="default-user",
        seed_synthetic=False,
    )
    token = set_authenticated_scope(AuthenticatedScope("verified-org", "verified-user"))
    try:
        repository.learners.save(
            LearnerProfile(id="verified-learner", code="S-VERIFY", age=7)
        )
        assert repository.learners.get("verified-learner") is not None
    finally:
        reset_authenticated_scope(token)

    assert repository.learners.get("verified-learner") is None
    assert (
        repository.for_scope("verified-org", "verified-user").learners.get(
            "verified-learner"
        )
        is not None
    )
