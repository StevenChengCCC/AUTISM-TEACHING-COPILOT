from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.main import app
from app.services.v2_upload_security_service import V2UploadSecurityService


def test_upload_metadata_rejects_dangerous_extensions():
    service = V2UploadSecurityService(Settings(_env_file=None))

    with pytest.raises(ValidationError):
        service.validate_upload_metadata("IEP summary.pdf.exe", "application/pdf", 10)
    with pytest.raises(ValidationError):
        service.validate_upload_metadata("visual-card.jpg.php", "image/jpeg", 10)
    with pytest.raises(ValidationError):
        service.validate_upload_metadata("profile.docm", None, 10)
    with pytest.raises(ValidationError):
        service.validate_upload_metadata("records.zip", None, 10)
    with pytest.raises(ValidationError):
        service.validate_upload_metadata("script.svg", None, 10)


def test_upload_metadata_rejects_oversized_uploads():
    config = Settings(_env_file=None, MAX_UPLOAD_BYTES=5)
    service = V2UploadSecurityService(config)

    with pytest.raises(ValidationError, match="exceeds"):
        service.validate_upload_metadata("notes.txt", "text/plain", 6)


def test_safe_storage_name_uses_uuid_and_preserves_safe_extension():
    service = V2UploadSecurityService(Settings(_env_file=None))

    stored_name = service.safe_storage_name("IEP summary.pdf")

    assert stored_name.endswith(".pdf")
    assert "IEP" not in stored_name
    assert len(stored_name.removesuffix(".pdf")) == 32


def test_file_signature_validation_rejects_extension_mismatch():
    service = V2UploadSecurityService(Settings(_env_file=None))

    service.validate_file_signature("card.png", b"\x89PNG\r\n\x1a\nimage")
    service.validate_file_signature("summary.pdf", b"%PDF-1.7")
    service.validate_file_signature("profile.docx", b"PK\x03\x04docx")

    with pytest.raises(ValidationError):
        service.validate_file_signature("summary.pdf", b"<html>not a pdf</html>")
    with pytest.raises(ValidationError):
        service.validate_file_signature("card.jpg", b"\x89PNG\r\n\x1a\nimage")


def test_record_endpoint_rejects_unsafe_json_uploads_and_sanitizes_text():
    client = TestClient(app)

    unsafe = client.post(
        "/api/v2/learners/a102/records",
        json={
            "fileName": "learner-notes.pdf.exe",
            "fileType": "PDF",
            "text": "demo",
        },
    )
    assert unsafe.status_code == 422

    clean = client.post(
        "/api/v2/learners/a102/records",
        json={
            "fileName": "sanitized-notes.txt",
            "fileType": "TXT",
            "text": "Useful note\x00 with bad control \x07character.",
        },
    )
    assert clean.status_code == 201
    assert "\x00" not in clean.json()["extractedText"]
    assert "\x07" not in clean.json()["extractedText"]
    assert "Useful note" in clean.json()["extractedText"]


def test_quarantine_storage_is_not_publicly_served():
    client = TestClient(app)

    response = client.get("/storage/quarantine/example.txt")

    assert response.status_code == 404
