from app.schemas.v2_dto import (
    LearnerRecord,
    LearnerRecordDto,
    RecordCreate,
    RecordUploadRequest,
    utc_now,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_repositories import V2Repositories, repositories


class V2RecordService:
    """Metadata-only record service; blob storage and parsers will replace fake extraction."""

    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos
        self.learners = V2LearnerService(repos)

    def list_for_learner(self, learner_id: str) -> list[LearnerRecord]:
        self.learners.get(learner_id)
        return self.repos.records.for_learner(learner_id)

    def list_dtos_for_learner(self, learner_id: str) -> list[LearnerRecordDto]:
        return [self.to_dto(record) for record in self.list_for_learner(learner_id)]

    def create(self, learner_id: str, payload: RecordCreate) -> LearnerRecord:
        self.learners.get(learner_id)
        record = LearnerRecord(id=self.repos.next_id("record"), learner_id=learner_id, file_name=payload.file_name, file_type=payload.file_type, status="ready", uploaded_at=utc_now(), extracted_text=payload.pasted_text or "Mock extraction pending real parser integration.")
        return self.repos.records.save(record)

    def create_dto(
        self, learner_id: str, payload: RecordUploadRequest
    ) -> LearnerRecordDto:
        record = self.create(
            learner_id,
            RecordCreate(
                file_name=payload.fileName,
                file_type=payload.fileType,
                pasted_text=payload.text,
            ),
        )
        return self.to_dto(record)

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
        )
