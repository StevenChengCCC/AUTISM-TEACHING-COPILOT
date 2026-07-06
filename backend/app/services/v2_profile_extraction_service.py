from app.integrations.ai_provider import V2AIProvider
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.schemas.v2_dto import LearnerProfileExtractionDto
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_record_service import V2RecordService
from app.services.v2_repositories import V2Repositories, repositories


class V2ProfileExtractionService:
    def __init__(self, repos: V2Repositories = repositories, ai: V2AIProvider | None = None):
        self.learners = V2LearnerService(repos)
        self.records = V2RecordService(repos)
        self.ai = ai or MockV2AIProvider()

    def extract(self, learner_id: str) -> LearnerProfileExtractionDto:
        learner = self.learners.get(learner_id)
        records = self.records.list_for_learner(learner_id)
        extracted, insights = self.ai.extract_profile(learner, records)
        return LearnerProfileExtractionDto(
            learner=self.learners.to_dto(extracted),
            records=[self.records.to_dto(record) for record in records],
            insights=insights,
            analyzedRecordCount=len(records),
            status="complete",
        )
