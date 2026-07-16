from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from uuid import uuid4

from app.core.config import Settings, settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.integrations.private_object_storage import (
    PrivateObjectStorage,
    get_private_object_storage,
)
from app.schemas.v2_dto import (
    LearnerRecord,
    LearnerRecordDto,
    RecordCreate,
    RecordDeletionResponse,
    RecordTextCorrectionRequest,
    RecordUploadCompleteRequest,
    RecordUploadIntentRequest,
    RecordUploadIntentResponse,
    RecordUploadRequest,
    utc_now,
)
from app.services.v2_document_parser_service import (
    DocumentParsingError,
    V2DocumentParserService,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_upload_security_service import (
    V2UploadSecurityService,
    upload_security_service,
)


_UNSAFE_DISPLAY_CHARS = re.compile(r"[\x00-\x1f\x7f]")
logger = logging.getLogger(__name__)


class V2RecordService:
    """Owns private upload, validation, parsing, correction, and deletion state."""

    def __init__(
        self,
        repos: V2Repositories = repositories,
        upload_security: V2UploadSecurityService = upload_security_service,
        storage: PrivateObjectStorage | None = None,
        parser: V2DocumentParserService | None = None,
        config: Settings = settings,
    ):
        self.repos = repos
        self.learners = V2LearnerService(repos)
        self.upload_security = upload_security
        self.storage = storage or get_private_object_storage(config)
        self.parser = parser or V2DocumentParserService(config)
        self.config = config

    def list_for_learner(self, learner_id: str) -> list[LearnerRecord]:
        self.learners.get(learner_id)
        return self.repos.records.for_learner(learner_id)

    def list_dtos_for_learner(self, learner_id: str) -> list[LearnerRecordDto]:
        return [self.to_dto(record) for record in self.list_for_learner(learner_id)]

    def get_for_learner(self, learner_id: str, record_id: str) -> LearnerRecord:
        self.learners.get(learner_id)
        record = self.repos.records.get(record_id)
        if not record or record.learner_id != learner_id:
            raise NotFoundError("Learner record not found")
        return record

    def create_upload_intent(
        self, learner_id: str, payload: RecordUploadIntentRequest
    ) -> RecordUploadIntentResponse:
        self.learners.get(learner_id)
        file_name = self._safe_display_name(payload.fileName)
        self.upload_security.validate_upload_metadata(
            file_name=file_name,
            content_type=payload.contentType,
            size_bytes=payload.sizeBytes,
        )
        extension = Path(file_name).suffix.lower()
        object_key = (
            f"{self.config.S3_UPLOAD_PREFIX.strip('/')}/"
            f"{uuid4().hex}/{uuid4().hex}{extension}"
        )
        signed = self.storage.create_presigned_put(object_key, payload.contentType)
        record = LearnerRecord(
            id=self.repos.next_id("record"),
            learner_id=learner_id,
            file_name=file_name,
            file_type=extension.removeprefix(".").upper(),
            status="upload_pending",
            uploaded_at=utc_now(),
            storage_key=object_key,
            declared_content_type=payload.contentType,
            expected_size_bytes=payload.sizeBytes,
            malware_scan_status="not_configured",
            parsing_message="Waiting for the private object upload to complete.",
        )
        saved = self.repos.records.save(record)
        return RecordUploadIntentResponse(
            record=self.to_dto(saved),
            uploadUrl=signed.url,
            requiredHeaders=signed.required_headers,
            expiresAt=signed.expires_at.isoformat(),
        )

    def complete_upload(
        self,
        learner_id: str,
        record_id: str,
        payload: RecordUploadCompleteRequest,
    ) -> LearnerRecordDto:
        record = self.get_for_learner(learner_id, record_id)
        if record.status not in {"upload_pending", "uploaded"}:
            raise ConflictError("This upload completion was already processed.")
        if not record.storage_key:
            raise ValidationError("The learner record has no private object key.")

        record = self.repos.records.save(
            record.model_copy(
                update={
                    "status": "uploaded",
                    "upload_completed_at": datetime.now(timezone.utc),
                    "parsing_message": "Private object upload confirmed.",
                }
            )
        )
        record = self.repos.records.save(
            record.model_copy(
                update={
                    "status": "validating",
                    "parsing_message": "Verifying the uploaded object.",
                }
            )
        )
        try:
            metadata = self.storage.head(record.storage_key)
            if metadata.key != record.storage_key:
                raise ValidationError("Uploaded object key verification failed.")
            if metadata.size_bytes != record.expected_size_bytes:
                raise ValidationError(
                    "Uploaded object size did not match the upload intent."
                )
            if (
                metadata.content_type.split(";", 1)[0].strip().lower()
                != record.declared_content_type.split(";", 1)[0].strip().lower()
            ):
                raise ValidationError(
                    "Uploaded object content type did not match the upload intent."
                )
            self.upload_security.validate_upload_metadata(
                record.file_name,
                record.declared_content_type,
                metadata.size_bytes,
            )
            data = self.storage.read_bytes(
                record.storage_key, self.config.MAX_UPLOAD_BYTES
            )
            self.upload_security.validate_file_signature(record.file_name, data)
            scan = self.upload_security.scan_file_for_malware(record.storage_key)
            if scan.status == "failed":
                failed = self.repos.records.save(
                    record.model_copy(
                        update={
                            "status": "failed",
                            "object_size_bytes": metadata.size_bytes,
                            "malware_scan_status": "failed",
                            "parsing_message": scan.message,
                        }
                    )
                )
                return self.to_dto(failed)
            record = self.repos.records.save(
                record.model_copy(
                    update={
                        "status": "parsing",
                        "object_size_bytes": metadata.size_bytes,
                        "malware_scan_status": scan.status,
                        "parsing_message": "Parsing the uploaded document.",
                    }
                )
            )
            parsed = self.parser.parse(record.file_name, data)
            status = (
                "needs_ocr"
                if parsed.needs_ocr
                else "needs_review" if parsed.needs_review else "ready"
            )
            record = self.repos.records.save(
                record.model_copy(
                    update={
                        "status": status,
                        "extracted_text": self.upload_security.sanitize_untrusted_record_text(
                            parsed.text
                        ),
                        "extraction_method": parsed.extraction_method,
                        "parsing_message": parsed.message,
                    }
                )
            )
            return self.to_dto(record)
        except DocumentParsingError as exc:
            logger.warning(
                "record_parsing_failure",
                extra={
                    "event": "record_parsing_failure",
                    "error_code": "record_parsing_failure",
                    "error_category": type(exc).__name__,
                },
            )
            failed = self.repos.records.save(
                record.model_copy(
                    update={
                        "status": "failed",
                        "parsing_message": str(exc),
                    }
                )
            )
            return self.to_dto(failed)
        except ValidationError as exc:
            self.repos.records.save(
                record.model_copy(
                    update={"status": "failed", "parsing_message": exc.message}
                )
            )
            raise

    def save_correction(
        self,
        learner_id: str,
        record_id: str,
        payload: RecordTextCorrectionRequest,
    ) -> LearnerRecordDto:
        record = self.get_for_learner(learner_id, record_id)
        corrected = self.upload_security.sanitize_untrusted_record_text(
            payload.correctedText
        ).strip()
        if not corrected:
            raise ValidationError("Corrected record text cannot be empty.")
        if payload.expectedVersion is not None:
            record = record.model_copy(update={"version": payload.expectedVersion})
        saved = self.repos.records.save(
            record.model_copy(
                update={
                    "teacher_corrected_text": corrected,
                    "status": "reviewed",
                    "parsing_message": "Teacher-corrected text saved for profile review.",
                }
            )
        )
        return self.to_dto(saved)

    def delete_record(self, learner_id: str, record_id: str) -> RecordDeletionResponse:
        record = self.get_for_learner(learner_id, record_id)
        pending = self.repos.records.save(
            record.model_copy(update={"deletion_status": "pending"})
        )
        if pending.storage_key:
            try:
                self.storage.delete(pending.storage_key)
            except Exception:
                latest = self.repos.records.get(record_id) or pending
                self.repos.records.save(
                    latest.model_copy(
                        update={
                            "deletion_status": "failed",
                            "parsing_message": "Object deletion failed and can be retried.",
                        }
                    )
                )
                return RecordDeletionResponse(
                    recordId=record_id,
                    status="deletion_failed",
                    retryable=True,
                    message="The original object could not be deleted. Retry deletion.",
                )
        self.repos.records.delete(record_id, expected_version=pending.version)
        return RecordDeletionResponse(
            recordId=record_id,
            status="deleted",
            retryable=False,
            message="The original object and extracted record text were deleted.",
        )

    def create(self, learner_id: str, payload: RecordCreate) -> LearnerRecord:
        """Compatibility path for teacher-pasted text; no binary is implied."""

        self.learners.get(learner_id)
        file_name = self._safe_display_name(payload.file_name)
        extracted_text = self.upload_security.sanitize_untrusted_record_text(
            payload.pasted_text
        )
        estimated_size = len(extracted_text.encode("utf-8", errors="ignore"))
        self.upload_security.validate_upload_metadata(
            file_name=file_name,
            content_type=self._content_type_from_file_type(payload.file_type),
            size_bytes=estimated_size,
        )
        record = LearnerRecord(
            id=self.repos.next_id("record"),
            learner_id=learner_id,
            file_name=file_name,
            file_type=self._normalized_file_type(file_name, payload.file_type),
            status="reviewed",
            uploaded_at=utc_now(),
            extracted_text=extracted_text,
            teacher_corrected_text=extracted_text,
            extraction_method="teacher_paste",
            expected_size_bytes=estimated_size,
            object_size_bytes=estimated_size,
            malware_scan_status="not_configured",
            parsing_message="Teacher-pasted text saved; no binary file was uploaded.",
        )
        return self.repos.records.save(record)

    def create_dto(
        self, learner_id: str, payload: RecordUploadRequest
    ) -> LearnerRecordDto:
        return self.to_dto(
            self.create(
                learner_id,
                RecordCreate(
                    file_name=payload.fileName,
                    file_type=payload.fileType,
                    pasted_text=payload.text,
                ),
            )
        )

    @staticmethod
    def to_dto(record: LearnerRecord) -> LearnerRecordDto:
        return LearnerRecordDto(
            id=record.id,
            learnerId=record.learner_id,
            fileName=record.file_name,
            fileType=record.file_type,
            status=record.status,
            uploadedAt=record.uploaded_at.isoformat(),
            extractedText=record.extracted_text,
            teacherCorrectedText=record.teacher_corrected_text,
            effectiveText=record.effective_text,
            malwareScanStatus=record.malware_scan_status,
            parsingMessage=record.parsing_message,
            deletionStatus=record.deletion_status,
            objectSizeBytes=record.object_size_bytes,
            version=record.version,
        )

    @staticmethod
    def _safe_display_name(value: str) -> str:
        name = Path(_UNSAFE_DISPLAY_CHARS.sub("", value or "")).name.strip()
        if not name:
            raise ValidationError("Upload file name is required.")
        return name[:255]

    @staticmethod
    def _normalized_file_type(file_name: str, provided_file_type: str) -> str:
        extension = file_name.rsplit(".", 1)[-1].upper()
        return extension or provided_file_type.strip().upper()

    @staticmethod
    def _content_type_from_file_type(file_type: str) -> str | None:
        return {
            "TXT": "text/plain",
            "PDF": "application/pdf",
            "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get((file_type or "").strip().upper())
