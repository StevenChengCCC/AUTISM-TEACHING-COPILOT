from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


ReleaseClassification = Literal[
    "Not ready", "Demo ready", "Controlled pilot ready", "Pilot ready"
]


@dataclass(frozen=True)
class StudyThresholds:
    """Frozen before results are entered; changing the version requires review."""

    version: str = "teacher-usability-v1"
    minimum_overall_task_completion_percent: float = 90.0
    minimum_critical_task_completion_percent: float = 100.0
    maximum_median_task_seconds: dict[str, float] | None = None
    maximum_worst_case_multiplier: float = 2.0
    maximum_assisted_or_error_task_percent: float = 10.0
    minimum_print_readability_median_5: float = 4.0
    minimum_print_usefulness_median_5: float = 4.0
    maximum_critical_issues: int = 0
    maximum_open_high_issues: int = 0
    minimum_participants_reporting_time_saved_percent: float = 80.0
    minimum_median_estimated_time_saved_percent: float = 20.0

    def __post_init__(self) -> None:
        if self.maximum_median_task_seconds is None:
            object.__setattr__(
                self,
                "maximum_median_task_seconds",
                {
                    "prepare_package": 900,
                    "locate_and_print_subset": 120,
                    "start_session": 60,
                    "record_valid_trial": 20,
                    "recover_after_reload_or_conflict": 120,
                    "complete_closeout": 300,
                },
            )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReleaseEvidence:
    synthetic_evidence_complete: bool = False
    no_open_critical_technical_failures: bool = False
    privacy_security_review_complete: bool = False
    authorized_nonproduction_smoke_complete: bool = False
    physical_printer_evidence_complete: bool = False
    teacher_study_participants: int = 0
    teacher_study_thresholds_met: bool = False
    production_auth_tenant_storage_download_verified: bool = False
    backup_restore_and_rollback_verified: bool = False
    monitoring_and_support_ownership_verified: bool = False
    retention_and_deletion_verified: bool = False
    high_findings_closed_or_accepted: bool = False


def classify_release(evidence: ReleaseEvidence) -> ReleaseClassification:
    """Fail closed. BLOCKED evidence never satisfies a boolean prerequisite."""

    if not evidence.synthetic_evidence_complete:
        return "Not ready"
    controlled = all(
        (
            evidence.no_open_critical_technical_failures,
            evidence.privacy_security_review_complete,
            evidence.authorized_nonproduction_smoke_complete,
            evidence.physical_printer_evidence_complete,
            3 <= evidence.teacher_study_participants <= 5,
            evidence.teacher_study_thresholds_met,
        )
    )
    if not controlled:
        return "Demo ready"
    pilot = all(
        (
            evidence.production_auth_tenant_storage_download_verified,
            evidence.backup_restore_and_rollback_verified,
            evidence.monitoring_and_support_ownership_verified,
            evidence.retention_and_deletion_verified,
            evidence.high_findings_closed_or_accepted,
        )
    )
    return "Pilot ready" if pilot else "Controlled pilot ready"
