from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserTaskResult:
    taskId: str
    status: str
    systemDurationMs: int
    interactionCount: int
    unexpectedDetours: int
    consoleErrors: int
    networkErrors: int
    evidence: str

    def validate(self) -> None:
        if self.status not in {"PASS", "FAIL", "BLOCKED"}:
            raise ValueError("Invalid browser smoke status.")
        if (
            min(
                self.systemDurationMs,
                self.interactionCount,
                self.unexpectedDetours,
                self.consoleErrors,
                self.networkErrors,
            )
            < 0
        ):
            raise ValueError("Browser smoke counts cannot be negative.")
        if not self.evidence or "http" in self.evidence.casefold():
            raise ValueError(
                "Evidence must be a privacy-safe local description, not a URL."
            )


def validate_browser_smoke_report(payload: dict[str, object]) -> None:
    if payload.get("schemaVersion") != "browser-smoke-v1":
        raise ValueError("Unsupported browser smoke schema.")
    if payload.get("timingKind") != "system_automation_not_teacher_time":
        raise ValueError(
            "Browser timings must not be represented as teacher completion time."
        )
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("At least one browser task result is required.")
    for item in tasks:
        if not isinstance(item, dict):
            raise ValueError("Invalid browser task result.")
        BrowserTaskResult(**item).validate()
