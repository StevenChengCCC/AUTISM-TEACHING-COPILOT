from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Header, Request
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient
from sqlalchemy.orm import Session

from app.core.auth_context import (
    AuthenticatedScope,
    reset_authenticated_scope,
    set_authenticated_scope,
)
from app.core.config import Settings, settings
from app.core.exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    SessionExpiredError,
)
from app.domain.models import ChildProfile, Teacher, TeacherChildAccess

PERMISSION_RANK = {"viewer": 1, "editor": 2, "admin": 3}
_PUBLIC_V2_PATHS = {"/api/v2/health"}
_SIGNED_STORAGE_PREFIXES = (
    "/api/v2/uploads/local/",
    "/api/v2/exports/local/",
)


@dataclass(frozen=True)
class CurrentTeacher:
    id: int | str | None
    role: str = "teacher"
    organization_id: int | None = None
    organization_external_id: str | None = None
    user_external_id: str | None = None
    subject: str | None = None
    email: str | None = None
    display_name: str = "Teacher"
    expires_at: int | None = None
    authentication_mode: str = "demo"
    is_anonymous: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class OIDCJWTValidator:
    """Validate Cognito JWTs without trusting browser-supplied identity fields."""

    def __init__(
        self,
        config: Settings = settings,
        jwks_client: PyJWKClient | None = None,
    ) -> None:
        self.config = config
        self._jwks_client = jwks_client

    def _client(self) -> PyJWKClient:
        issuer = self.config.cognito_issuer
        if not issuer or not self.config.COGNITO_APP_CLIENT_ID:
            raise AuthenticationError(
                "Authentication is not configured for this environment."
            )
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                f"{issuer}/.well-known/jwks.json",
                cache_keys=True,
                lifespan=300,
                timeout=5,
            )
        return self._jwks_client

    def validate(self, token: str) -> dict[str, Any]:
        issuer = self.config.cognito_issuer
        client_id = self.config.COGNITO_APP_CLIENT_ID
        if not issuer or not client_id:
            raise AuthenticationError(
                "Authentication is not configured for this environment."
            )
        try:
            signing_key = self._client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=issuer,
                options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
            )
        except ExpiredSignatureError as exc:
            raise SessionExpiredError(
                "Your session expired. Sign in again to continue."
            ) from exc
        except (InvalidTokenError, ValueError, RuntimeError) as exc:
            raise AuthenticationError(
                "The sign-in session could not be verified."
            ) from exc

        token_use = claims.get("token_use")
        audience = claims.get("aud")
        access_client_id = claims.get("client_id")
        if token_use not in {"access", "id"}:
            raise AuthenticationError("The sign-in session could not be verified.")
        if token_use == "access" and access_client_id != client_id:
            raise AuthenticationError("The sign-in session could not be verified.")
        if token_use == "id" and audience != client_id:
            raise AuthenticationError("The sign-in session could not be verified.")
        return claims


@lru_cache(maxsize=1)
def get_oidc_validator() -> OIDCJWTValidator:
    return OIDCJWTValidator(settings)


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("Sign in to continue.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Sign in to continue.")
    return token.strip()


def _teacher_from_claims(claims: dict[str, Any]) -> CurrentTeacher:
    subject = str(claims["sub"])
    organization_id = claims.get(settings.COGNITO_ORGANIZATION_CLAIM)
    if not organization_id:
        organization_id = settings.COGNITO_DEFAULT_ORGANIZATION_ID
    groups = claims.get("cognito:groups") or []
    role = "admin" if settings.COGNITO_ADMIN_GROUP in groups else "teacher"
    display_name = str(
        claims.get("name")
        or claims.get("given_name")
        or claims.get("email")
        or "Teacher"
    )
    return CurrentTeacher(
        id=subject,
        role=role,
        organization_external_id=str(organization_id),
        user_external_id=f"cognito-{subject}",
        subject=subject,
        email=str(claims["email"]) if claims.get("email") else None,
        display_name=display_name,
        expires_at=int(claims["exp"]),
        authentication_mode="cognito",
    )


def _demo_teacher(x_teacher_id: str | None) -> CurrentTeacher:
    if settings.APP_ENV not in {"development", "test"}:
        raise AuthenticationError("Sign in to continue.")
    if x_teacher_id:
        external_id = f"demo-teacher-{x_teacher_id}"
        return CurrentTeacher(
            id=x_teacher_id,
            role="teacher",
            organization_external_id=settings.V2_DEFAULT_ORGANIZATION_ID,
            user_external_id=external_id,
            display_name="Demo Teacher",
            authentication_mode="demo",
        )
    if settings.DEV_ALLOW_ANON_TEACHER:
        return CurrentTeacher(
            id=settings.DEV_ANON_TEACHER_ID,
            role="admin",
            organization_external_id=settings.V2_DEFAULT_ORGANIZATION_ID,
            user_external_id=settings.V2_DEFAULT_USER_ID,
            display_name="Demo Teacher",
            authentication_mode="demo",
            is_anonymous=True,
        )
    raise AuthenticationError("Sign in to continue.")


async def get_current_teacher(
    request: Request,
    authorization: str | None = Header(default=None),
    x_teacher_id: str | None = Header(default=None),
) -> AsyncGenerator[CurrentTeacher, None]:
    """Authenticate once and bind ownership scope for the complete request."""

    path = request.url.path
    is_public = (
        path in _PUBLIC_V2_PATHS
        or path.startswith(_SIGNED_STORAGE_PREFIXES)
        or path.startswith("/api/v2/dev/")
    )
    if is_public:
        teacher = CurrentTeacher(
            id=None,
            role="viewer",
            organization_external_id=settings.V2_DEFAULT_ORGANIZATION_ID,
            user_external_id=settings.V2_DEFAULT_USER_ID,
            authentication_mode="public",
            is_anonymous=True,
        )
    elif settings.effective_auth_mode == "cognito":
        claims = get_oidc_validator().validate(_bearer_token(authorization))
        teacher = _teacher_from_claims(claims)
    else:
        teacher = _demo_teacher(x_teacher_id)

    scope_token = set_authenticated_scope(
        AuthenticatedScope(
            organization_external_id=(
                teacher.organization_external_id
                or settings.V2_DEFAULT_ORGANIZATION_ID
            ),
            user_external_id=teacher.user_external_id or settings.V2_DEFAULT_USER_ID,
        )
    )
    request.state.current_teacher = teacher
    try:
        yield teacher
    finally:
        reset_authenticated_scope(scope_token)


def load_teacher(db: Session, current: CurrentTeacher) -> CurrentTeacher:
    if current.is_anonymous:
        return current
    if not isinstance(current.id, int):
        raise ForbiddenError("This legacy operation is unavailable for this account.")
    teacher = db.query(Teacher).filter(Teacher.id == current.id).first()
    if not teacher:
        raise ForbiddenError("Teacher not found")
    return CurrentTeacher(
        id=teacher.id, role=teacher.role, organization_id=teacher.organization_id
    )


def require_child_access(
    db: Session, child_id: int, current: CurrentTeacher, permission: str = "viewer"
) -> ChildProfile:
    teacher = load_teacher(db, current)
    child = db.query(ChildProfile).filter(ChildProfile.id == child_id).first()
    if not child:
        raise NotFoundError("Child profile not found")
    if teacher.is_admin and (
        teacher.organization_id is None
        or child.organization_id == teacher.organization_id
    ):
        return child
    access = (
        db.query(TeacherChildAccess)
        .filter(
            TeacherChildAccess.teacher_id == teacher.id,
            TeacherChildAccess.child_id == child_id,
        )
        .first()
    )
    if (
        not access
        or PERMISSION_RANK.get(access.permission_level, 0)
        < PERMISSION_RANK[permission]
    ):
        raise ForbiddenError("Insufficient child access")
    return child


def require_admin(db: Session, current: CurrentTeacher) -> CurrentTeacher:
    teacher = load_teacher(db, current)
    if not teacher.is_admin:
        raise ForbiddenError("Admin permission required")
    return teacher
