from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SyntheticSmokeResult:
    caseId: str
    label: str
    stage: str
    status: str
    durationMs: int
    evidence: str
    failure: str | None = None


class V2SyntheticSmokeService:
    """Runs named deterministic local tests; external dependencies are never replaced."""

    def __init__(self, backend_root: Path, corpus_path: Path | None = None):
        self.backend_root = backend_root
        self.corpus_path = (
            corpus_path
            or backend_root / "tests/fixtures/round16g_synthetic_smoke_cases.json"
        )

    def load_cases(self) -> list[dict[str, str]]:
        payload = json.loads(self.corpus_path.read_text(encoding="utf-8"))
        if payload.get("schemaVersion") != "synthetic-smoke-corpus-v1":
            raise ValueError("Unsupported synthetic smoke corpus version.")
        cases = payload.get("cases", [])
        if len(cases) < 12:
            raise ValueError("At least 12 synthetic smoke cases are required.")
        if len({item["caseId"] for item in cases}) != len(cases):
            raise ValueError("Synthetic smoke case IDs must be unique.")
        return cases

    def run(self) -> dict[str, object]:
        results: list[SyntheticSmokeResult] = []
        environment = {
            **os.environ,
            "APP_ENV": "test",
            "AI_PROVIDER": "mock",
            "AI_FAILURE_MODE": "fail_closed",
            "USABILITY_TELEMETRY_ENABLED": "false",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
        for case in self.load_cases():
            started = time.perf_counter()
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", case["testNode"]],
                cwd=self.backend_root,
                capture_output=True,
                text=True,
                env=environment,
                timeout=300,
            )
            duration = int((time.perf_counter() - started) * 1000)
            output = (completed.stdout + "\n" + completed.stderr).strip()
            failure = None if completed.returncode == 0 else output[-2000:]
            results.append(
                SyntheticSmokeResult(
                    caseId=case["caseId"],
                    label=case["label"],
                    stage=case["stage"],
                    status="PASS" if completed.returncode == 0 else "FAIL",
                    durationMs=duration,
                    evidence=case["testNode"],
                    failure=failure,
                )
            )
        return {
            "schemaVersion": "synthetic-smoke-report-v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "externalProvidersUsed": False,
            "realLearnerDataUsed": False,
            "overallStatus": (
                "PASS" if all(item.status == "PASS" for item in results) else "FAIL"
            ),
            "caseCount": len(results),
            "results": [item.__dict__ for item in results],
        }


def render_synthetic_smoke_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Synthetic end-to-end smoke evidence",
        "",
        f"Overall: **{report['overallStatus']}**",
        f"Cases: {report['caseCount']}",
        "External providers used: no",
        "Real learner data used: no",
        "",
        "| Case | Pipeline stage | Result | System time | Evidence |",
        "|---|---|---:|---:|---|",
    ]
    for item in report["results"]:
        lines.append(
            f"| {item['caseId']} — {item['label']} | {item['stage']} | **{item['status']}** | {item['durationMs']} ms | `{item['evidence']}` |"
        )
        if item.get("failure"):
            lines.extend(
                (
                    "",
                    f"## {item['caseId']} failure",
                    "",
                    "```text",
                    item["failure"],
                    "```",
                )
            )
    return "\n".join(lines) + "\n"
