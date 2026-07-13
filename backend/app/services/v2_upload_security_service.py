from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, settings
from app.core.exceptions import ValidationError


_DANGEROUS_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".html",
    ".htm",
    ".js",
    ".mjs",
    ".php",
    ".ps1",
    ".scr",
    ".sh",
    ".svg",
    ".vbs",
}
_ARCHIVE_EXTENSIONS = {".7z", ".gz", ".rar", ".tar", ".zip"}
_MACRO_OFFICE_EXTENSIONS = {".docm", ".pptm", ".xlsm"}
_CONTROL_CHARS_EXCEPT_COMMON_WHITESPACE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class UploadScanResult:
    status: str
    message: str


class V2UploadSecurityService:
    """Backend-side safeguards for untrusted learner record uploads.

    Current v2 routes accept JSON metadata and extracted/pasted text only. The
    binary helpers here are deliberately reusable for the future multipart upload
    endpoint, where raw files should enter quarantine before parsing.
    """

    def __init__(self, config: Settings = settings):
        self.config = config

    def validate_upload_metadata(
        self,
        file_name: str,
        content_type: str | None = None,
        size_bytes: int | None = None,
    ) -> None:
        normalized_name = (file_name or "").strip()
        if not normalized_name:
            raise ValidationError("Upload file name is required.")

        extension = self._safe_extension(normalized_name)
        suffixes = [suffix.lower() for suffix in Path(normalized_name).suffixes]
        dangerous_suffixes = (
            _DANGEROUS_EXTENSIONS | _ARCHIVE_EXTENSIONS | _MACRO_OFFICE_EXTENSIONS
        )
        dangerous_matches = [suffix for suffix in suffixes if suffix in dangerous_suffixes]
        if dangerous_matches:
            raise ValidationError(
                f"Unsupported or unsafe upload extension: {dangerous_matches[-1]}"
            )

        if len(suffixes) > 1 and suffixes[-1] in _DANGEROUS_EXTENSIONS:
            raise ValidationError("Dangerous double extension uploads are not allowed.")

        if extension not in self.config.allowed_upload_extension_set:
            raise ValidationError(f"Unsupported upload extension: {extension}")

        if size_bytes is not None:
            if size_bytes < 0:
                raise ValidationError("Upload size cannot be negative.")
            if size_bytes > self.config.MAX_UPLOAD_BYTES:
                raise ValidationError(
                    f"Upload exceeds the {self.config.MAX_UPLOAD_BYTES} byte limit."
                )

        if content_type:
            normalized_content_type = content_type.split(";")[0].strip().lower()
            if (
                normalized_content_type
                and normalized_content_type not in self.config.allowed_upload_mime_type_set
            ):
                raise ValidationError(
                    f"Unsupported upload content type: {normalized_content_type}"
                )

    def safe_storage_name(self, original_file_name: str) -> str:
        extension = self._safe_extension(original_file_name)
        if extension not in self.config.allowed_upload_extension_set:
            raise ValidationError(f"Unsupported upload extension: {extension}")
        return f"{uuid.uuid4().hex}{extension}"

    def detect_file_signature(self, file_bytes: bytes) -> str:
        if file_bytes.startswith(b"%PDF-"):
            return "pdf"
        if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if file_bytes.startswith(b"\xff\xd8\xff"):
            return "jpeg"
        if file_bytes.startswith(b"PK\x03\x04"):
            return "zip"
        try:
            file_bytes.decode("utf-8")
            return "txt"
        except UnicodeDecodeError:
            return "unknown"

    def validate_file_signature(self, file_name: str, file_bytes: bytes) -> None:
        extension = self._safe_extension(file_name)
        signature = self.detect_file_signature(file_bytes)
        if extension == ".pdf" and signature != "pdf":
            raise ValidationError("Uploaded PDF signature did not match its extension.")
        if extension == ".png" and signature != "png":
            raise ValidationError("Uploaded PNG signature did not match its extension.")
        if extension in {".jpg", ".jpeg"} and signature != "jpeg":
            raise ValidationError("Uploaded JPEG signature did not match its extension.")
        if extension == ".docx" and signature != "zip":
            raise ValidationError("Uploaded DOCX signature did not match its extension.")
        if extension == ".txt" and signature not in {"txt", "unknown"}:
            raise ValidationError("Uploaded TXT signature did not match its extension.")

    def scan_file_for_malware(self, file_path: str | Path) -> UploadScanResult:
        if not self.config.ENABLE_UPLOAD_ANTIVIRUS_SCAN:
            return UploadScanResult(
                status="skipped",
                message=(
                    "Antivirus scanning is disabled for this demo. Production should "
                    "scan quarantined files with ClamAV, cloud malware scanning, or a "
                    "private scanning service before marking files clean."
                ),
            )
        return UploadScanResult(
            status="unavailable",
            message=(
                "Antivirus scanning was requested, but no scanner is configured. "
                "Do not send private learner records to public scanning APIs by default."
            ),
        )

    def sanitize_untrusted_record_text(self, text: str | None) -> str:
        raw_text = text or ""
        without_nulls = raw_text.replace("\x00", "")
        cleaned = _CONTROL_CHARS_EXCEPT_COMMON_WHITESPACE.sub("", without_nulls)
        max_chars = self.config.MAX_UNTRUSTED_RECORD_TEXT_CHARS
        return cleaned[:max_chars]

    def wrap_untrusted_record_text(self, text: str | None) -> str:
        sanitized = self.sanitize_untrusted_record_text(text)
        return (
            "<untrusted_learner_record>\n"
            f"{sanitized}\n"
            "</untrusted_learner_record>"
        )

    @staticmethod
    def _safe_extension(file_name: str) -> str:
        extension = Path(file_name.strip()).suffix.lower()
        if not extension:
            raise ValidationError("Upload file extension is required.")
        return extension


upload_security_service = V2UploadSecurityService()


def sanitize_untrusted_record_text(text: str | None) -> str:
    return upload_security_service.sanitize_untrusted_record_text(text)
