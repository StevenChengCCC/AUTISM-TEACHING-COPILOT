from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.schemas.v2_dto import LearnerProfileExtractionDto
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_record_service import V2RecordService
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_upload_security_service import (
    V2UploadSecurityService,
    upload_security_service,
)


class V2ProfileExtractionService:
    def __init__(
        self,
        repos: V2Repositories = repositories,
        ai: V2AIProvider | None = None,
        upload_security: V2UploadSecurityService = upload_security_service,
    ):
        self.learners = V2LearnerService(repos)
        self.records = V2RecordService(repos)
        self.ai = ai or get_v2_ai_provider()
        self.upload_security = upload_security

    def extract(self, learner_id: str) -> LearnerProfileExtractionDto:
        learner = self.learners.get(learner_id)
        records = self.records.list_for_learner(learner_id)
        records_for_ai = [
            record.model_copy(
                update={
                    "extracted_text": self.upload_security.wrap_untrusted_record_text(
                        record.extracted_text
                    )
                }
            )
            for record in records
        ]
        extracted, insights = self.ai.extract_profile(learner, records_for_ai)
        return LearnerProfileExtractionDto(
            learner=self.learners.to_dto(extracted),
            records=[self.records.to_dto(record) for record in records],
            insights=insights,
            analyzedRecordCount=len(records),
            status="complete",
        )
