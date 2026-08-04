from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.api.v2_routes import (
    _printable_lesson_kit_service,
    _private_object_storage,
)
from app.core import auth as auth_module
from app.core.exceptions import (
    ConflictError,
    ObjectStorageUnavailableError,
)
from app.integrations.private_object_storage import LocalPrivateObjectStorage
from app.main import app
from app.schemas.v2_dto import PrintableLessonKitRequest
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_repositories import V2Repositories
from test_v2_printable_lesson_kit import _seed_package, _settings


def _request(materials):
    return PrintableLessonKitRequest(
        materialIds=[item.id for item in materials],
        pageSize="Letter",
        reviewedConfirmation=True,
    )


def _service(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_package(repos)
    storage = LocalPrivateObjectStorage(config)
    return (
        V2PrintableLessonKitService(repos, storage, config),
        repos,
        storage,
        package,
        materials,
    )


def test_canonical_artifact_contract_and_signed_get_headers(tmp_path):
    service, _repos, storage, package, materials = _service(tmp_path)
    client = TestClient(app)
    app.dependency_overrides[_printable_lesson_kit_service] = lambda: service
    app.dependency_overrides[_private_object_storage] = lambda: storage
    try:
        response = client.post(
            f"/api/v2/lesson-packages/{package.id}/pdf-artifacts",
            json=_request(materials).model_dump(mode="json", by_alias=True),
        )
        assert response.status_code == 201
        artifact = response.json()
        assert artifact["status"] == "ready"
        assert artifact["contentType"] == "application/pdf"
        assert artifact["sizeBytes"] > 0
        assert artifact["pageCount"] > 0
        assert artifact["filename"].endswith(".pdf")
        assert "storageObjectKey" not in artifact
        assert "private-storage" not in artifact["downloadUrl"]

        download = client.get(urlsplit(artifact["downloadUrl"]).path)
        assert download.status_code == 200
        assert download.content.startswith(b"%PDF-")
        assert int(download.headers["content-length"]) == len(download.content)
        assert download.headers["content-type"].startswith("application/pdf")
        assert "attachment" in download.headers["content-disposition"]
        assert artifact["filename"] in download.headers["content-disposition"]
        assert download.headers["x-content-type-options"] == "nosniff"
        assert download.headers["cache-control"] == "private, no-store"
    finally:
        app.dependency_overrides.pop(_printable_lesson_kit_service, None)
        app.dependency_overrides.pop(_private_object_storage, None)


def test_repeated_request_reuses_current_revision_and_refreshes_url(tmp_path):
    service, repos, _storage, package, materials = _service(tmp_path)
    first = service.create_artifact(package.id, _request(materials))
    second = service.create_artifact(package.id, _request(materials))

    assert first.reused is False
    assert second.reused is True
    assert second.artifactId == first.artifactId
    assert second.sha256 == first.sha256
    assert second.materialRevisions == first.materialRevisions
    assert datetime.fromisoformat(second.expiresAt.replace("Z", "+00:00")) >= datetime.fromisoformat(first.expiresAt.replace("Z", "+00:00"))
    assert len([
        job for job in repos.export_jobs.list()
        if getattr(job, "status", None) == "completed"
    ]) == 1


def test_changed_package_revision_does_not_serve_stale_artifact(tmp_path):
    service, repos, _storage, package, materials = _service(tmp_path)
    artifact = service.create_artifact(package.id, _request(materials))
    current = repos.lesson_packages.get(package.id)
    repos.lesson_packages.save(
        current.model_copy(update={"lessonBrief": "Teacher revised brief."})
    )

    with pytest.raises(ConflictError, match="stale"):
        service.create_download(artifact.artifactId)

    replacement = service.create_artifact(package.id, _request(materials))
    assert replacement.artifactId != artifact.artifactId
    assert replacement.packageRevision > artifact.packageRevision
    assert replacement.reused is False


def test_changed_material_revision_creates_a_new_artifact(tmp_path):
    service, repos, _storage, package, materials = _service(tmp_path)
    artifact = service.create_artifact(package.id, _request(materials))
    current = repos.materials.get(materials[0].id)
    repos.materials.save(
        current.model_copy(update={"teacherNotes": "Teacher revised material notes."})
    )

    replacement = service.create_artifact(package.id, _request(materials))

    assert replacement.artifactId != artifact.artifactId
    assert replacement.materialRevisions[materials[0].id] > (
        artifact.materialRevisions[materials[0].id]
    )
    assert replacement.reused is False


def test_missing_or_corrupt_artifact_fails_with_storage_error(tmp_path):
    service, repos, storage, package, materials = _service(tmp_path)
    artifact = service.create_artifact(package.id, _request(materials))
    job = repos.export_jobs.get(artifact.artifactId)
    storage.delete(job.storageObjectKey)

    with pytest.raises(ObjectStorageUnavailableError):
        service.create_download(artifact.artifactId)

    regenerated = service.create_artifact(package.id, _request(materials))
    regenerated_job = repos.export_jobs.get(regenerated.artifactId)
    storage._path(regenerated_job.storageObjectKey).write_bytes(b"not-a-pdf")
    with pytest.raises(ObjectStorageUnavailableError, match="valid PDF"):
        service.create_download(regenerated.artifactId)


def test_failed_storage_write_does_not_return_ready_metadata(tmp_path):
    class FailingStorage(LocalPrivateObjectStorage):
        def write_bytes(self, key, body, content_type):
            raise ObjectStorageUnavailableError("Synthetic storage failure")

    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_package(repos)
    service = V2PrintableLessonKitService(repos, FailingStorage(config), config)

    with pytest.raises(ObjectStorageUnavailableError):
        service.create_artifact(package.id, _request(materials))
    assert any(job.status == "failed" for job in repos.export_jobs.list())


def test_package_must_be_approved_before_artifact_creation(tmp_path):
    service, repos, _storage, package, materials = _service(tmp_path)
    current = repos.lesson_packages.get(package.id)
    repos.lesson_packages.save(current.model_copy(update={"status": "draft"}))

    with pytest.raises(ConflictError, match="Approve the lesson package"):
        service.create_artifact(package.id, _request(materials))


def test_unicode_filename_uses_rfc5987_header(tmp_path):
    service, _repos, storage, package, materials = _service(tmp_path)
    artifact = service.create_artifact(package.id, _request(materials))
    job = service.repos.export_jobs.get(artifact.artifactId)
    signed = storage.create_presigned_get(job.storageObjectKey, "学习支持–N-482.pdf")
    client = TestClient(app)
    app.dependency_overrides[_private_object_storage] = lambda: storage
    try:
        response = client.get(urlsplit(signed.url).path)
    finally:
        app.dependency_overrides.pop(_private_object_storage, None)

    disposition = response.headers["content-disposition"]
    assert response.status_code == 200
    assert "filename*=UTF-8''" in disposition
    assert "%E5%AD%A6%E4%B9%A0" in disposition
    assert "\r" not in disposition and "\n" not in disposition


def test_pdf_artifact_endpoint_requires_authentication_in_strict_mode(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "APP_ENV", "staging")
    monkeypatch.setattr(auth_module.settings, "AUTH_MODE", "cognito")
    monkeypatch.setattr(auth_module.settings, "COGNITO_REGION", "us-east-1")
    monkeypatch.setattr(
        auth_module.settings, "COGNITO_USER_POOL_ID", "us-east-1_synthetic"
    )
    monkeypatch.setattr(
        auth_module.settings, "COGNITO_APP_CLIENT_ID", "public-browser-client"
    )

    response = TestClient(app).post(
        "/api/v2/lesson-packages/not-authorized/pdf-artifacts",
        json={"materialIds": [], "reviewedConfirmation": True},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
