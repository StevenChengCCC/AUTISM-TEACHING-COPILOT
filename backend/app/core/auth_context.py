from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedScope:
    organization_external_id: str
    user_external_id: str


_scope: ContextVar[AuthenticatedScope | None] = ContextVar(
    "authenticated_repository_scope", default=None
)


def get_authenticated_scope() -> AuthenticatedScope | None:
    return _scope.get()


def set_authenticated_scope(scope: AuthenticatedScope) -> Token:
    return _scope.set(scope)


def reset_authenticated_scope(token: Token) -> None:
    _scope.reset(token)
