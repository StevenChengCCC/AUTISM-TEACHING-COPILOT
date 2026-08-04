from __future__ import annotations

import json
import logging
import time
from typing import Any


logger = logging.getLogger("app.generation")

_SENSITIVE_KEYS = {
    "prompt", "teacher_request", "teacherRequest", "record", "record_text",
    "evidence", "extracted_text", "extractedText", "learner_code", "learnerCode",
}


def privacy_safe_metadata(values: dict[str, Any]) -> dict[str, Any]:
    """Allow operational dimensions while refusing learner content and prompts."""

    safe: dict[str, Any] = {}
    for key, value in values.items():
        if key in _SENSITIVE_KEYS or any(token in key.casefold() for token in ("prompt", "record", "evidence")):
            safe[key] = "[REDACTED]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, list):
            safe[key] = len(value)
        else:
            safe[key] = type(value).__name__
    return safe


def emit_generation_metric(
    metric: str,
    value: float,
    *,
    unit: str = "Count",
    stage: str = "package",
    provider: str = "unknown",
    status: str = "unknown",
    environment: str = "development",
    **metadata: Any,
) -> None:
    """Emit CloudWatch-EMF-compatible, low-cardinality structured logs."""

    event = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "AutismTeachingCopilot/Generation",
                "Dimensions": [["Environment", "Stage", "Provider", "Status"]],
                "Metrics": [{"Name": metric, "Unit": unit}],
            }],
        },
        "Environment": environment,
        "Stage": stage,
        "Provider": provider,
        "Status": status,
        metric: value,
        "event": "generation_metric",
        **privacy_safe_metadata(metadata),
    }
    logger.info(json.dumps(event, separators=(",", ":"), sort_keys=True))
