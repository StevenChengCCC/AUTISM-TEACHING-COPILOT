"""Explicitly authorized, synthetic-only staging smoke.

Skipped by default. It creates an idempotent PDF artifact and starts/resumes the
designated synthetic session, so authorization and a non-production target are
required even though it does not invoke an AI provider.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import requests


AUTHORIZED = os.getenv("RUN_AUTHORIZED_STAGING_SMOKE") == "true"
pytestmark = pytest.mark.skipif(
    not AUTHORIZED,
    reason="Requires explicit authorization and a designated synthetic staging target.",
)


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.fail(f"Missing required staging smoke setting: {name}", pytrace=False)
    return value


def _ok(response: requests.Response, step: str) -> dict:
    if not response.ok:
        pytest.fail(
            f"{step} failed with HTTP {response.status_code}; response body suppressed.",
            pytrace=False,
        )
    return response.json()


def test_authorized_synthetic_staging_download_and_session_lineage():
    base = _required("ATC_STAGING_API_BASE").rstrip("/")
    if "localhost" in base or not base.startswith("https://"):
        pytest.fail(
            "Staging API must be an explicit HTTPS non-local target.", pytrace=False
        )
    token_path = Path(_required("ATC_STAGING_TOKEN_FILE"))
    token = token_path.read_text(encoding="utf-8").strip()
    package_id = _required("ATC_STAGING_SYNTHETIC_PACKAGE_ID")
    session_id = _required("ATC_STAGING_SYNTHETIC_SESSION_ID")
    context_ids = json.loads(_required("ATC_STAGING_SYNTHETIC_CONTEXT_IDS_JSON"))
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    ready = requests.get(f"{base}/health/ready", headers=headers, timeout=20)
    assert (
        ready.status_code == 200
    ), "Dependency readiness failed; response body suppressed."
    package = _ok(
        requests.get(
            f"{base}/api/v2/lesson-packages/{package_id}", headers=headers, timeout=20
        ),
        "package lookup",
    )
    readiness = _ok(
        requests.get(
            f"{base}/api/v2/lesson-packages/{package_id}/print-readiness",
            headers=headers,
            timeout=20,
        ),
        "print readiness",
    )
    assert readiness["ready"] is True
    _ok(
        requests.get(
            f"{base}/api/v2/lesson-packages/{package_id}/print-presets",
            params={"pageSize": "Letter", "textProfile": "standard"},
            headers=headers,
            timeout=20,
        ),
        "preset catalog",
    )
    artifact = _ok(
        requests.post(
            f"{base}/api/v2/lesson-packages/{package_id}/pdf-artifacts",
            json={
                "materialIds": [],
                "printPreset": "teacher_desk",
                "pageSize": "Letter",
                "locale": "en-US",
                "tableOfContents": True,
                "pageNumbers": True,
                "textProfile": "standard",
                "reviewedConfirmation": True,
            },
            headers=headers,
            timeout=60,
        ),
        "PDF creation",
    )
    download = _ok(
        requests.post(
            f"{base}/api/v2/printable-lesson-kits/{artifact['artifactId']}/download",
            headers=headers,
            timeout=20,
        ),
        "authenticated download preparation",
    )
    pdf = requests.get(download["downloadUrl"], timeout=60)
    assert (
        pdf.status_code == 200
        and pdf.content.startswith(b"%PDF-")
        and len(pdf.content) > 1000
    )
    run = _ok(
        requests.post(
            f"{base}/api/v2/sessions/{session_id}/start",
            json={
                "idempotencyKey": "round16g-authorized-staging-smoke-v1",
                "startedByTeacher": "synthetic-staging-smoke",
                "expectedPackageRevision": package["version"],
                "contextIds": context_ids,
                "pdfExportId": artifact["artifactId"],
                "printPreset": "teacher_desk",
            },
            headers=headers,
            timeout=30,
        ),
        "session start",
    )
    assert run["snapshot"]["packageRevision"] == package["version"]
    assert run["snapshot"]["pdfArtifact"]["artifactId"] == artifact["artifactId"]
