from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.integrations.private_object_storage import (
    LocalPrivateObjectStorage,
    S3PrivateObjectStorage,
)
from app.main import app
from app.schemas.v2_dto import (
    RecordTextCorrectionRequest,
    RecordUploadCompleteRequest,
    RecordUploadIntentRequest,
    LearnerProfile,
)
from app.services.v2_document_parser_service import V2DocumentParserService
from app.services.v2_record_service import V2RecordService
from app.services.v2_repositories import V2Repositories
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories
from app.services.v2_upload_security_service import V2UploadSecurityService


PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        _env_file=None,
        APP_ENV="test",
        OBJECT_STORAGE_PROVIDER="local",
        LOCAL_PRIVATE_STORAGE_DIR=str(tmp_path / "private-records"),
        PUBLIC_API_BASE_URL="http://testserver",
        LOCAL_UPLOAD_SIGNING_SECRET="test-only-signing-secret",
    )
    values.update(overrides)
    return Settings(**values)


def _service(tmp_path: Path) -> tuple[V2RecordService, LocalPrivateObjectStorage]:
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    service = V2RecordService(
        V2Repositories(),
        V2UploadSecurityService(config),
        storage,
        V2DocumentParserService(config),
        config,
    )
    return service, storage


def _pdf(text: str) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 720, text)
    document.save()
    return output.getvalue()


def _blank_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def _docx(text: str) -> bytes:
    output = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    return output.getvalue()


def _upload(
    service: V2RecordService,
    storage: LocalPrivateObjectStorage,
    *,
    name: str,
    content_type: str,
    data: bytes,
):
    intent = service.create_upload_intent(
        "a102",
        RecordUploadIntentRequest(
            fileName=name, contentType=content_type, sizeBytes=len(data)
        ),
    )
    token = intent.uploadUrl.rsplit("/", 1)[-1]
    storage.put_presigned(token, data, content_type)
    return service.complete_upload(
        "a102", intent.record.id, RecordUploadCompleteRequest()
    )


@pytest.mark.parametrize(
    ("name", "content_type", "data", "expected"),
    [
        (
            "notes.txt",
            "text/plain",
            b"A small independent request for help.",
            "independent",
        ),
        (
            "profile.pdf",
            PDF_MIME,
            _pdf("Learner uses a short phrase to ask for help."),
            "short phrase",
        ),
        (
            "plan.docx",
            DOCX_MIME,
            _docx("Use visual prompts and wait time."),
            "visual prompts",
        ),
    ],
)
def test_real_txt_pdf_and_docx_parsing(tmp_path, name, content_type, data, expected):
    service, storage = _service(tmp_path)
    record = _upload(service, storage, name=name, content_type=content_type, data=data)
    assert record.status == "needs_review"
    assert expected in record.extractedText
    assert record.malwareScanStatus == "not_configured"
    assert record.objectSizeBytes == len(data)


def test_image_only_pdf_requires_ocr_and_does_not_silently_continue(tmp_path):
    service, storage = _service(tmp_path)
    record = _upload(
        service,
        storage,
        name="scanned.pdf",
        content_type=PDF_MIME,
        data=_blank_pdf(),
    )
    assert record.status == "needs_ocr"
    assert "OCR" in record.parsingMessage
    assert record.effectiveText == ""


def test_profile_extraction_refuses_only_unreviewed_ocr_record(tmp_path):
    config = _settings(tmp_path)
    repositories = V2Repositories()
    repositories.learners.save(LearnerProfile(id="ocr-learner", code="S-OCR", age=7))
    storage = LocalPrivateObjectStorage(config)
    service = V2RecordService(
        repositories,
        V2UploadSecurityService(config),
        storage,
        V2DocumentParserService(config),
        config,
    )
    intent = service.create_upload_intent(
        "ocr-learner",
        RecordUploadIntentRequest(
            fileName="scanned.pdf",
            contentType=PDF_MIME,
            sizeBytes=len(_blank_pdf()),
        ),
    )
    storage.put_presigned(intent.uploadUrl.rsplit("/", 1)[-1], _blank_pdf(), PDF_MIME)
    service.complete_upload(
        "ocr-learner", intent.record.id, RecordUploadCompleteRequest()
    )
    with pytest.raises(ValidationError, match="OCR"):
        V2ProfileExtractionService(repositories).extract("ocr-learner")


def test_metadata_rejects_invalid_extension_mime_and_oversize(tmp_path):
    service, _ = _service(tmp_path)
    with pytest.raises(ValidationError):
        service.create_upload_intent(
            "a102",
            RecordUploadIntentRequest(
                fileName="unsafe.exe",
                contentType="application/octet-stream",
                sizeBytes=10,
            ),
        )
    with pytest.raises(ValidationError):
        service.create_upload_intent(
            "a102",
            RecordUploadIntentRequest(
                fileName="notes.pdf", contentType="text/plain", sizeBytes=10
            ),
        )
    with pytest.raises(ValidationError):
        service.create_upload_intent(
            "a102",
            RecordUploadIntentRequest(
                fileName="notes.txt",
                contentType="text/plain",
                sizeBytes=10 * 1024 * 1024 + 1,
            ),
        )


def test_signed_key_tampering_cross_learner_and_duplicate_completion_are_rejected(
    tmp_path,
):
    service, storage = _service(tmp_path)
    data = b"Teacher observation with enough readable text."
    intent = service.create_upload_intent(
        "a102",
        RecordUploadIntentRequest(
            fileName="notes.txt", contentType="text/plain", sizeBytes=len(data)
        ),
    )
    token = intent.uploadUrl.rsplit("/", 1)[-1]
    with pytest.raises(ValidationError):
        storage.put_presigned(f"{token}tampered", data, "text/plain")
    storage.put_presigned(token, data, "text/plain")
    with pytest.raises(PydanticValidationError):
        RecordUploadCompleteRequest.model_validate(
            {"objectKey": "attacker-controlled/key.txt"}
        )
    with pytest.raises(NotFoundError):
        service.complete_upload("b214", intent.record.id, RecordUploadCompleteRequest())
    service.complete_upload("a102", intent.record.id, RecordUploadCompleteRequest())
    with pytest.raises(ConflictError):
        service.complete_upload("a102", intent.record.id, RecordUploadCompleteRequest())


def test_post_upload_object_size_is_verified(tmp_path):
    service, storage = _service(tmp_path)
    intended = b"intended bytes"
    actual = b"different uploaded bytes and length"
    intent = service.create_upload_intent(
        "a102",
        RecordUploadIntentRequest(
            fileName="notes.txt",
            contentType="text/plain",
            sizeBytes=len(intended),
        ),
    )
    storage.put_presigned(intent.uploadUrl.rsplit("/", 1)[-1], actual, "text/plain")
    with pytest.raises(ValidationError):
        service.complete_upload("a102", intent.record.id, RecordUploadCompleteRequest())


def test_signature_mismatch_and_parsing_failure(tmp_path, caplog):
    service, storage = _service(tmp_path)
    data = b"not a real PDF"
    intent = service.create_upload_intent(
        "a102",
        RecordUploadIntentRequest(
            fileName="fake.pdf", contentType=PDF_MIME, sizeBytes=len(data)
        ),
    )
    storage.put_presigned(intent.uploadUrl.rsplit("/", 1)[-1], data, PDF_MIME)
    with pytest.raises(ValidationError):
        service.complete_upload("a102", intent.record.id, RecordUploadCompleteRequest())
    assert service.get_for_learner("a102", intent.record.id).status == "failed"

    malformed = b"%PDF-1.4\nmalformed"
    failed = _upload(
        service,
        storage,
        name="malformed.pdf",
        content_type=PDF_MIME,
        data=malformed,
    )
    assert failed.status == "failed"
    assert "could not be parsed" in failed.parsingMessage
    assert "record_parsing_failure" in caplog.text
    assert "malformed" not in caplog.text


def test_teacher_correction_and_private_object_deletion(tmp_path):
    service, storage = _service(tmp_path)
    record = _upload(
        service,
        storage,
        name="notes.txt",
        content_type="text/plain",
        data=b"Initial parser text long enough for review.",
    )
    internal = service.get_for_learner("a102", record.id)
    object_path = storage._path(internal.storage_key or "")
    assert object_path.is_file()
    corrected = service.save_correction(
        "a102",
        record.id,
        RecordTextCorrectionRequest(
            correctedText="Teacher corrected text with a small participation win.",
            expectedVersion=record.version,
        ),
    )
    assert corrected.status == "reviewed"
    assert corrected.effectiveText.startswith("Teacher corrected")
    result = service.delete_record("a102", record.id)
    assert result.status == "deleted"
    assert not object_path.exists()
    with pytest.raises(NotFoundError):
        service.get_for_learner("a102", record.id)


def test_failed_object_deletion_is_visible_and_retryable(tmp_path):
    config = _settings(tmp_path)

    class FailOnceStorage(LocalPrivateObjectStorage):
        should_fail = True

        def delete(self, key: str) -> None:
            if self.should_fail:
                self.should_fail = False
                raise RuntimeError("synthetic storage failure")
            super().delete(key)

    storage = FailOnceStorage(config)
    service = V2RecordService(
        V2Repositories(),
        V2UploadSecurityService(config),
        storage,
        V2DocumentParserService(config),
        config,
    )
    record = _upload(
        service,
        storage,
        name="delete-retry.txt",
        content_type="text/plain",
        data=b"Synthetic record for a deletion retry test.",
    )
    first = service.delete_record("a102", record.id)
    assert first.status == "deletion_failed"
    assert first.retryable is True
    assert service.get_for_learner("a102", record.id).deletion_status == "failed"
    second = service.delete_record("a102", record.id)
    assert second.status == "deleted"


def test_private_upload_has_no_get_route():
    response = TestClient(app).get("/api/v2/uploads/local/not-a-token")
    assert response.status_code in {404, 405}


def test_complete_http_upload_review_correction_and_delete_flow():
    client = TestClient(app)
    file_name = f"synthetic-{uuid4().hex}.txt"
    data = b"Synthetic classroom note with enough text for teacher review."
    intent_response = client.post(
        "/api/v2/learners/a102/records/upload-intent",
        json={
            "fileName": file_name,
            "contentType": "text/plain",
            "sizeBytes": len(data),
        },
    )
    assert intent_response.status_code == 201
    intent = intent_response.json()
    assert "storageKey" not in intent["record"]
    upload_path = urlparse(intent["uploadUrl"]).path
    upload_response = client.put(
        upload_path,
        content=data,
        headers=intent["requiredHeaders"],
    )
    assert upload_response.status_code == 204
    record_id = intent["record"]["id"]
    tampered_completion = client.post(
        f"/api/v2/learners/a102/records/{record_id}/complete",
        json={"objectKey": "attacker-controlled/key.txt"},
    )
    assert tampered_completion.status_code == 422
    complete = client.post(
        f"/api/v2/learners/a102/records/{record_id}/complete", json={}
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "needs_review"
    corrected = client.patch(
        f"/api/v2/learners/a102/records/{record_id}/extracted-text",
        json={
            "correctedText": "Teacher-confirmed synthetic record text.",
            "expectedVersion": complete.json()["version"],
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "reviewed"
    deleted = client.delete(f"/api/v2/learners/a102/records/{record_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


class _FakeS3Client:
    def __init__(self):
        self.presign = None
        self.deleted = None

    def generate_presigned_url(self, operation, **kwargs):
        self.presign = (operation, kwargs)
        return "https://private-bucket.example/signed-put"

    def delete_object(self, **kwargs):
        self.deleted = kwargs


def test_s3_presign_is_server_controlled_private_and_encrypted(tmp_path):
    client = _FakeS3Client()
    config = _settings(
        tmp_path,
        OBJECT_STORAGE_PROVIDER="s3",
        S3_BUCKET="private-demo-bucket",
        S3_REGION="us-east-1",
    )
    storage = S3PrivateObjectStorage(config, client)
    signed = storage.create_presigned_put(
        "learner-records/random/random.txt", "text/plain"
    )
    assert signed.url.startswith("https://private-bucket.example")
    assert signed.required_headers["x-amz-server-side-encryption"] == "AES256"
    params = client.presign[1]["Params"]
    assert params["Bucket"] == "private-demo-bucket"
    assert params["Key"] == "learner-records/random/random.txt"
    assert "ACL" not in params
    storage.delete("learner-records/random/random.txt")
    assert client.deleted == {
        "Bucket": "private-demo-bucket",
        "Key": "learner-records/random/random.txt",
    }


def test_extracted_and_teacher_corrected_text_survive_repository_recreation(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'records.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    config = _settings(
        tmp_path,
        V2_REPOSITORY_MODE="sqlalchemy",
        V2_SEED_SYNTHETIC_DATA=False,
    )
    repository = SQLAlchemyV2Repositories(
        factory,
        config,
        organization_external_id="upload-org",
        user_external_id="upload-teacher",
        seed_synthetic=False,
    )
    repository.learners.save(
        LearnerProfile(id="upload-learner", code="S-UPLOAD", age=7)
    )
    storage = LocalPrivateObjectStorage(config)
    service = V2RecordService(
        repository,
        V2UploadSecurityService(config),
        storage,
        V2DocumentParserService(config),
        config,
    )
    data = b"Extracted text persists after a backend repository restart."
    intent = service.create_upload_intent(
        "upload-learner",
        RecordUploadIntentRequest(
            fileName="persistent.txt",
            contentType="text/plain",
            sizeBytes=len(data),
        ),
    )
    storage.put_presigned(intent.uploadUrl.rsplit("/", 1)[-1], data, "text/plain")
    parsed = service.complete_upload(
        "upload-learner", intent.record.id, RecordUploadCompleteRequest()
    )
    service.save_correction(
        "upload-learner",
        parsed.id,
        RecordTextCorrectionRequest(
            correctedText="Teacher correction persists too.",
            expectedVersion=parsed.version,
        ),
    )

    restarted_repository = SQLAlchemyV2Repositories(
        factory,
        config,
        organization_external_id="upload-org",
        user_external_id="upload-teacher",
        seed_synthetic=False,
    )
    restarted = restarted_repository.records.get(parsed.id)
    assert restarted is not None
    assert restarted.extracted_text.startswith("Extracted text persists")
    assert restarted.teacher_corrected_text == "Teacher correction persists too."
    assert restarted.storage_key and "S-UPLOAD" not in restarted.storage_key
    other_owner = restarted_repository.for_scope("upload-org", "other-teacher")
    assert other_owner.records.get(parsed.id) is None
    other_organization = restarted_repository.for_scope(
        "other-upload-org", "upload-teacher"
    )
    assert other_organization.records.get(parsed.id) is None
    engine.dispose()
