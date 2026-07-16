from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any


_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_SAFE_EXTRA_FIELDS = {
    "duration_ms",
    "environment",
    "error_category",
    "error_code",
    "event",
    "incomplete_capabilities",
    "method",
    "path",
    "readiness",
    "request_id",
    "status_code",
}


def set_request_id(request_id: str) -> Token[str]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


class MinimizedJsonFormatter(logging.Formatter):
    """CloudWatch-friendly JSON that only emits explicitly safe metadata."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "requestId": getattr(record, "request_id", None) or get_request_id(),
        }
        for field in _SAFE_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None and field != "request_id":
                payload[field] = value
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if any(
        getattr(handler, "_lesson_kit_structured", False) for handler in root.handlers
    ):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(MinimizedJsonFormatter())
    handler._lesson_kit_structured = True  # type: ignore[attr-defined]
    root.addHandler(handler)
