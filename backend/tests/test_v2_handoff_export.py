from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from pypdf import PdfReader
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.core.exceptions import ConflictError
from app.integrations.private_object_storage import (
    LocalPrivateObjectStorage,
    S3PrivateObjectStorage,
)
from app.main import app
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    LearnerProfile,
    LessonPackageDto,
    ProgressDataPointDto,
    TeacherHandoffExportRequest,
)
from app.services.v2_handoff_export_service import V2HandoffExportService
from app.services.v2_repositories import V2Repositories
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories


def _settings(tmp_path, **overrides) -> Settings:
    values = {
        "_env_file": None,
        "APP_ENV": "test",
        "V2_REPOSITORY_MODE": "memory",
        "OBJECT_STORAGE_PROVIDER": "local",
        "LOCAL_PRIVATE_STORAGE_DIR": str(tmp_path / "private"),
        "LOCAL_UPLOAD_SIGNING_SECRET": "test-export-signing-secret",
        "PUBLIC_API_BASE_URL": "http://testserver",
        "EXPORT_RETENTION_DAYS": 7,
    }
    values.update(overrides)
    return Settings(**values)


def _seed_approved(repos: V2Repositories) -> tuple[LessonPackageDto, list[GeneratedMaterialDto]]:
    materials = [
        GeneratedMaterialDto(
            id="approved-help-card",
            packageId="approved-package",
            type="help_card",
            title="Help Card",
            status="approved",
            content={"instruction": "Help, please.", "imageAltText": "A help symbol."},
            printLayout={"pageSize": "Letter", "orientation": "portrait", "color": "blue"},
        ),
        GeneratedMaterialDto(
            id="unapproved-token-board",
            packageId="approved-package",
            type="token_board",
            title="Draft Token Board",
            status="teacher_review_needed",
            content={"instruction": "Earn five stars."},
            printLayout={"pageSize": "Letter", "orientation": "portrait", "color": "blue"},
        ),
    ]
    package = LessonPackageDto(
        id="approved-package",
        learnerId="a102",
        draftId="draft-approved",
        goal="Ask for help using a short phrase",
        duration="10–12 min",
        theme="Vehicles",
        lessonBrief="Teach a short help request with visual support.",
        teachingFlow=[],
        materials=materials,
        summaryTemplate="Record prompting, participation, and small wins.",
        status="approved",
        aiProvider="mock",
    )
    repos.lesson_packages.save(package)
    for material in materials:
        repos.generated_materials.save(material)
    return package, materials


def _completed_export(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_approved(repos)
    repos.progress_data.save(
        ProgressDataPointDto(
            id="formula-progress",
            learnerId="a102",
            sessionDate="2025-05-13",
            goal="Asking for Help",
            opportunities=4,
            accuracyPercent=50,
            independencePercent=45,
            promptLevel="Level 2",
            signalsHighlighted=["engagement"],
            teacherNotes="=HYPERLINK(\"https://unsafe.invalid\")",
        )
    )
    storage = LocalPrivateObjectStorage(config)
    service = V2HandoffExportService(repos, storage, config)
    request = TeacherHandoffExportRequest(
        packageIds=[package.id],
        materialIds=[item.id for item in materials],
        transitionNotes="Continue honoring established communication access.",
        reviewedConfirmation=True,
    )
    job = service.create("a102", request)
    assert job.status == "completed"
    assert job.storageObjectKey
    bundle = storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
    return service, repos, storage, job, bundle


def test_real_zip_pdf_csv_json_and_default_exclusions(tmp_path):
    _, _, _, job, bundle = _completed_export(tmp_path)
    assert "a102" not in (job.storageObjectKey or "")
    with ZipFile(BytesIO(bundle)) as archive:
        names = archive.namelist()
        assert names == job.manifest
        assert names == [
            "handoff-summary.pdf",
            "progress-data.csv",
            "handoff-data.json",
            "material-01-help_card.pdf",
            "README.txt",
        ]
        summary = archive.read("handoff-summary.pdf")
        assert summary.startswith(b"%PDF")
        assert len(PdfReader(BytesIO(summary)).pages) >= 2
        assert archive.read("material-01-help_card.pdf").startswith(b"%PDF")
        csv_text = archive.read("progress-data.csv").decode("utf-8-sig")
        assert "'=HYPERLINK" in csv_text
        data = json.loads(archive.read("handoff-data.json"))
        assert data["exportSchemaVersion"] == "teacher-handoff-v1"
        assert data["provenance"]["contentPolicy"] == "approved-content-only"
        serialized = json.dumps(data)
        for excluded in (
            "extractedText",
            "providerResponse",
            "systemPrompt",
            "imageBase64",
            "auditEvents",
            "OPENAI_API_KEY",
        ):
            assert excluded not in serialized
        assert [item["id"] for item in data["approvedMaterials"]] == ["approved-help-card"]
        readme = archive.read("README.txt").decode("utf-8")
        assert "Original uploaded documents and raw extracted text" in readme
        assert "not a claim of legal compliance" in readme


def test_date_filter_and_approved_content_filtering(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, _ = _seed_approved(repos)
    service = V2HandoffExportService(repos, LocalPrivateObjectStorage(config), config)
    request = TeacherHandoffExportRequest(
        packageIds=[package.id],
        dateRange={"startDate": "2025-05-01", "endDate": "2025-05-06"},
        includePrintableMaterials=False,
        reviewedConfirmation=True,
    )
    job = service.create("a102", request)
    bundle = service.storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
    with ZipFile(BytesIO(bundle)) as archive:
        data = json.loads(archive.read("handoff-data.json"))
        assert [item["sessionDate"] for item in data["progressData"]] == ["2025-05-05"]
        assert not any(name.startswith("material-") for name in archive.namelist())


def test_download_history_expiration_and_deletion(tmp_path):
    service, repos, storage, job, _ = _completed_export(tmp_path)
    signed = service.create_download(job.exportId)
    token = signed.downloadUrl.rsplit("/", 1)[-1]
    body, content_type, filename = storage.read_presigned_get(token)
    assert body.startswith(b"PK")
    assert content_type == "application/zip"
    assert filename == "teacher-handoff.zip"
    assert service.get(job.exportId).downloadCount == 1
    assert service.list("a102")[0].exportId == job.exportId

    deleted = service.delete(job.exportId)
    assert deleted.status == "deleted"
    assert not storage._path(job.storageObjectKey).exists()
    with pytest.raises(ConflictError):
        service.create_download(job.exportId)
    assert any(event["action"] == "download" for event in repos.audit_events)


def test_expiration_removes_private_artifact(tmp_path):
    service, repos, storage, job, _ = _completed_export(tmp_path)
    expired = job.model_copy(
        update={"expiresAt": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
    )
    repos.export_jobs.save(expired)
    refreshed = service.get(job.exportId)
    assert refreshed.status == "expired"
    assert not storage._path(job.storageObjectKey).exists()


def test_retry_failed_export_uses_new_persisted_job(tmp_path, caplog):
    class FailOnceStorage(LocalPrivateObjectStorage):
        failures = 1

        def write_bytes(self, key, body, content_type):
            if self.failures:
                self.failures -= 1
                raise RuntimeError("synthetic storage outage")
            return super().write_bytes(key, body, content_type)

    config = _settings(tmp_path)
    repos = V2Repositories()
    package, _ = _seed_approved(repos)
    service = V2HandoffExportService(repos, FailOnceStorage(config), config)
    failed = service.create(
        "a102",
        TeacherHandoffExportRequest(packageIds=[package.id], reviewedConfirmation=True),
    )
    assert failed.status == "failed"
    assert failed.errorCode == "EXPORT_GENERATION_FAILED"
    assert "export_failure" in caplog.text
    assert "synthetic storage outage" not in caplog.text
    retried = service.retry(failed.exportId)
    assert retried.status == "completed"
    assert retried.exportId != failed.exportId


def test_export_metadata_survives_repository_recreation(tmp_path):
    url = f"sqlite:///{tmp_path / 'exports.db'}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    config = _settings(
        tmp_path,
        V2_REPOSITORY_MODE="sqlalchemy",
        V2_SEED_SYNTHETIC_DATA=False,
    )
    repos = SQLAlchemyV2Repositories(
        factory,
        config,
        organization_external_id="org-export",
        user_external_id="teacher-export",
        seed_synthetic=False,
    )
    repos.learners.save(
        LearnerProfile(
            id="durable-learner",
            code="Synthetic Learner",
            age=8,
            profile_review_status="confirmed",
        )
    )
    material = GeneratedMaterialDto(
        id="durable-material",
        packageId="durable-package",
        type="help_card",
        title="Help Card",
        status="approved",
        content={"instruction": "Help, please."},
        printLayout={"pageSize": "Letter"},
    )
    repos.lesson_packages.save(
        LessonPackageDto(
            id="durable-package",
            learnerId="durable-learner",
            draftId="durable-draft",
            goal="Ask for help",
            duration="10 min",
            theme="Classroom",
            lessonBrief="Teacher-approved brief.",
            teachingFlow=[],
            materials=[material],
            summaryTemplate="Record small wins.",
            status="approved",
        )
    )
    repos.generated_materials.save(material)
    service = V2HandoffExportService(repos, LocalPrivateObjectStorage(config), config)
    job = service.create(
        "durable-learner",
        TeacherHandoffExportRequest(packageIds=["durable-package"], reviewedConfirmation=True),
    )
    restarted = SQLAlchemyV2Repositories(
        factory,
        config,
        organization_external_id="org-export",
        user_external_id="teacher-export",
        seed_synthetic=False,
    )
    persisted = V2HandoffExportService(
        restarted, LocalPrivateObjectStorage(config), config
    ).get(job.exportId)
    assert persisted.status == "completed"
    assert persisted.fileSizeBytes == job.fileSizeBytes
    assert persisted.storageObjectKey == job.storageObjectKey
    engine.dispose()


def test_s3_export_uses_private_encryption_and_short_lived_get(tmp_path):
    class FakeS3:
        def __init__(self):
            self.put = None
            self.presign = None
            self.deleted = None
            self.waited = None

        def put_object(self, **kwargs):
            self.put = kwargs

        def generate_presigned_url(self, operation, **kwargs):
            self.presign = (operation, kwargs)
            return "https://private.invalid/signed"

        def delete_object(self, **kwargs):
            self.deleted = kwargs

        def get_waiter(self, name):
            assert name == "object_not_exists"
            client = self

            class Waiter:
                def wait(self, **kwargs):
                    client.waited = kwargs

            return Waiter()

    client = FakeS3()
    config = _settings(
        tmp_path,
        OBJECT_STORAGE_PROVIDER="s3",
        S3_BUCKET="private-demo-bucket",
        S3_SERVER_SIDE_ENCRYPTION="AES256",
        EXPORT_DOWNLOAD_TTL_SECONDS=240,
    )
    storage = S3PrivateObjectStorage(config, client)
    storage.write_bytes("teacher-handoff-exports/aa/random.zip", b"PK", "application/zip")
    signed = storage.create_presigned_get("teacher-handoff-exports/aa/random.zip", "teacher-handoff.zip")
    assert signed.url.startswith("https://private.invalid")
    assert client.put["ServerSideEncryption"] == "AES256"
    assert "ACL" not in client.put
    operation, kwargs = client.presign
    assert operation == "get_object"
    assert kwargs["ExpiresIn"] == 240
    assert kwargs["Params"]["Bucket"] == "private-demo-bucket"
    storage.delete("teacher-handoff-exports/aa/random.zip")
    assert client.deleted["Key"] == "teacher-handoff-exports/aa/random.zip"
    assert client.waited["WaiterConfig"]["MaxAttempts"] == 5


def test_teacher_confirmation_is_required_by_schema():
    with pytest.raises(PydanticValidationError):
        TeacherHandoffExportRequest(reviewedConfirmation=False)


def test_handoff_http_create_history_download_and_delete_contract():
    client = TestClient(app)
    created = client.post(
        "/api/v2/learners/a102/handoff-exports",
        json={
            "sections": {
                "learnerOverview": True,
                "teachingStrategies": True,
                "activeGoals": True,
                "progress": True,
                "recentSessions": True,
                "lessonPackages": False,
                "approvedMaterials": False,
                "transitionNotes": True,
            },
            "dateRange": {},
            "sessionIds": [],
            "packageIds": [],
            "materialIds": [],
            "transitionNotes": "Synthetic authorized handoff note.",
            "includePrintableMaterials": False,
            "pageSize": "Letter",
            "orientation": "portrait",
            "reviewedConfirmation": True,
        },
    )
    assert created.status_code == 201
    job = created.json()
    assert job["status"] == "completed"
    assert "storageObjectKey" not in job

    history = client.get("/api/v2/handoff-exports?learnerId=a102")
    assert history.status_code == 200
    assert any(item["exportId"] == job["exportId"] for item in history.json())

    download = client.post(f"/api/v2/handoff-exports/{job['exportId']}/download")
    assert download.status_code == 200
    path = download.json()["downloadUrl"].replace("http://localhost:8000", "")
    artifact = client.get(path)
    assert artifact.status_code == 200
    assert artifact.content.startswith(b"PK")
    assert artifact.headers["content-type"].startswith("application/zip")

    deleted = client.delete(f"/api/v2/handoff-exports/{job['exportId']}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
