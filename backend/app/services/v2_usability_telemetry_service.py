from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from app.core.config import Settings


EventName = Literal[
    "task_started",
    "task_completed",
    "task_abandoned",
    "workflow_error",
    "retry",
    "assistance_requested",
    "task_rating",
]
TaskName = Literal[
    "prepare_package",
    "locate_and_print_subset",
    "start_session",
    "record_valid_trial",
    "recover_after_reload_or_conflict",
    "complete_closeout",
    "understand_progress_and_recommendation",
    "inspect_print_output",
    "compare_current_workflow",
]

_PSEUDONYM = re.compile(r"^P-[A-Z0-9]{3,12}$")
_CASE_ID = re.compile(r"^SYN-[A-Z0-9-]{2,24}$")
_SAFE_ERROR = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


@dataclass(frozen=True)
class UsabilityEvent:
    schemaVersion: str
    eventId: str
    participantId: str
    syntheticCaseId: str
    eventName: EventName
    taskName: TaskName
    occurredAt: str
    durationMs: int | None = None
    interactionCount: int | None = None
    rating: int | None = None
    outcome: Literal["success", "failure", "abandoned"] | None = None
    errorCategory: str | None = None

    def validate(self) -> None:
        if self.schemaVersion != "usability-event-v1":
            raise ValueError("Unsupported usability event schema version.")
        if not _PSEUDONYM.fullmatch(self.participantId):
            raise ValueError("Participant ID must be a study pseudonym.")
        if not _CASE_ID.fullmatch(self.syntheticCaseId):
            raise ValueError("Only synthetic study case IDs are accepted.")
        if self.durationMs is not None and not 0 <= self.durationMs <= 7_200_000:
            raise ValueError("Duration is outside the accepted study range.")
        if self.interactionCount is not None and not 0 <= self.interactionCount <= 1000:
            raise ValueError("Interaction count is outside the accepted study range.")
        if self.rating is not None and not 1 <= self.rating <= 5:
            raise ValueError("Ratings must be between 1 and 5.")
        if self.errorCategory is not None and not _SAFE_ERROR.fullmatch(
            self.errorCategory
        ):
            raise ValueError("Error category must be a predefined privacy-safe code.")
        datetime.fromisoformat(self.occurredAt.replace("Z", "+00:00"))


class V2UsabilityTelemetryService:
    """Opt-in, content-free event sink for small synthetic teacher studies."""

    def __init__(
        self, config: Settings, memory_sink: list[dict[str, object]] | None = None
    ):
        self.config = config
        self.memory_sink = memory_sink if memory_sink is not None else []

    @property
    def enabled(self) -> bool:
        return bool(
            self.config.USABILITY_TELEMETRY_ENABLED
            and self.config.USABILITY_TELEMETRY_SINK != "disabled"
            and self.config.APP_ENV in {"development", "test"}
        )

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "sink": (
                self.config.USABILITY_TELEMETRY_SINK if self.enabled else "disabled"
            ),
            "schemaVersion": "usability-event-v1",
            "retentionDays": self.config.USABILITY_TELEMETRY_RETENTION_DAYS,
            "contentCollection": False,
        }

    def record(self, event: UsabilityEvent, *, opted_in: bool) -> dict[str, object]:
        if not opted_in:
            raise PermissionError("Usability measurement requires explicit opt-in.")
        if not self.enabled:
            raise RuntimeError("Usability measurement is disabled.")
        event.validate()
        payload = asdict(event)
        if self.config.USABILITY_TELEMETRY_SINK == "memory":
            self.memory_sink.append(payload)
        elif self.config.USABILITY_TELEMETRY_SINK == "local_jsonl":
            path = Path(self.config.USABILITY_TELEMETRY_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return payload

    def export_participant(self, participant_id: str) -> list[dict[str, object]]:
        if not _PSEUDONYM.fullmatch(participant_id):
            raise ValueError("Invalid participant pseudonym.")
        return [
            item for item in self._all() if item.get("participantId") == participant_id
        ]

    def delete_participant(self, participant_id: str) -> int:
        if not _PSEUDONYM.fullmatch(participant_id):
            raise ValueError("Invalid participant pseudonym.")
        before = self._all()
        retained = [
            item for item in before if item.get("participantId") != participant_id
        ]
        self._replace(retained)
        return len(before) - len(retained)

    def purge_expired(self, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(
            days=self.config.USABILITY_TELEMETRY_RETENTION_DAYS
        )
        before = self._all()
        retained = [
            item
            for item in before
            if datetime.fromisoformat(str(item["occurredAt"]).replace("Z", "+00:00"))
            >= cutoff
        ]
        self._replace(retained)
        return len(before) - len(retained)

    def _all(self) -> list[dict[str, object]]:
        if self.config.USABILITY_TELEMETRY_SINK == "memory":
            return list(self.memory_sink)
        path = Path(self.config.USABILITY_TELEMETRY_PATH)
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _replace(self, items: list[dict[str, object]]) -> None:
        if self.config.USABILITY_TELEMETRY_SINK == "memory":
            self.memory_sink[:] = items
            return
        path = Path(self.config.USABILITY_TELEMETRY_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in items),
            encoding="utf-8",
        )
