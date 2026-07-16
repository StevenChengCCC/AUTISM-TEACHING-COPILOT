from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.core.exceptions import ValidationError
from app.schemas.v2_dto import (
    LearnerProfile,
    LearnerProfileExtractionDto,
    GenerationMetadataDto,
    ProfileExtractionResult,
    ProfileSignal,
)
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
        eligible_records = [
            record
            for record in records
            if record.status in {"ready", "reviewed"} and record.effective_text.strip()
        ]
        if records and not eligible_records:
            raise ValidationError(
                "Learner records still require parsing, OCR, or teacher text review before profile extraction."
            )
        records_for_ai = [
            record.model_copy(
                update={
                    "extracted_text": self.upload_security.wrap_untrusted_record_text(
                        record.effective_text
                    ),
                    "teacher_corrected_text": None,
                }
            )
            for record in eligible_records
        ]
        provider_result = self.ai.extract_profile(learner, records_for_ai)
        if isinstance(provider_result, tuple):
            # Compatibility for locally implemented providers using the earlier contract.
            extracted, insights = provider_result
            provider_result = ProfileExtractionResult(
                learner=extracted,
                profileSignals=extracted.profile_signals,
                unknownFields=extracted.unknown_fields,
                insights=insights,
            )
        saved = self.learners.save(self._merge_profile(learner, provider_result))
        metadata = getattr(self.ai, "last_generation_metadata", None)
        return LearnerProfileExtractionDto(
            learner=self.learners.to_dto(saved),
            records=[self.records.to_dto(record) for record in records],
            insights=provider_result.insights,
            profileSignals=saved.profile_signals,
            unknownFields=saved.unknown_fields,
            analyzedRecordCount=len(eligible_records),
            status="complete",
            generationStatus=metadata.status if metadata else None,
            generationMetadata=(
                GenerationMetadataDto.model_validate(
                    metadata.model_dump(mode="json", by_alias=True)
                )
                if metadata
                else None
            ),
        )

    @staticmethod
    def _merge_profile(
        current: LearnerProfile, result: ProfileExtractionResult
    ) -> LearnerProfile:
        """Merge suggestions without replacing teacher-entered non-empty values."""

        extracted = result.learner
        updates: dict[str, object] = {}
        all_extracted_signals = [*result.profile_signals, *extracted.profile_signals]

        def has_high_confidence(category: str) -> bool:
            return any(
                signal.category == category
                and signal.status != "rejected"
                and signal.confidence >= 0.75
                for signal in all_extracted_signals
            )

        evidence_categories = {
            "interests": "interest",
            "support_needs": "support_need",
            "reinforcement_preferences": "reinforcer",
            "strengths": "strength",
            "sensory_preferences": "sensory_preference",
            "known_challenges": "challenge",
            "prompting_preferences": "prompting",
            "current_goals": "goal",
        }
        list_fields = (
            "tags",
            "interests",
            "support_needs",
            "reinforcement_preferences",
            "strengths",
            "sensory_preferences",
            "known_challenges",
            "prompting_preferences",
            "current_goals",
            "response_options",
            "receptive_supports",
            "expressive_supports",
            "environmental_considerations",
            "effective_supports",
            "ineffective_supports",
            "mastered_skills",
            "emerging_skills",
            "break_preferences",
            "classroom_barriers",
        )
        scalar_fields = (
            "communication_mode",
            "attention_profile",
            "notes",
            "reading_level",
            "activity_duration_preference",
            "independence_profile",
            "generalization_profile",
        )
        for field in list_fields:
            existing_value = getattr(current, field)
            extracted_value = getattr(extracted, field)
            category = evidence_categories.get(field)
            can_populate = category is None or has_high_confidence(category)
            updates[field] = existing_value or (extracted_value if can_populate else [])
        for field in scalar_fields:
            existing_value = getattr(current, field)
            extracted_value = getattr(extracted, field)
            can_populate = field != "communication_mode" or has_high_confidence(
                "communication"
            )
            updates[field] = existing_value or (extracted_value if can_populate else "")

        def signal_key(signal: ProfileSignal) -> tuple[str, str, str]:
            evidence_key = (
                signal.evidence_fingerprint
                or signal.source_record_id
                or signal.source_location
                or "unsourced"
            )
            return (
                signal.category,
                signal.label.strip().casefold(),
                evidence_key,
            )

        existing_signals: dict[tuple[str, str, str], ProfileSignal] = {
            signal_key(signal): signal for signal in current.profile_signals
        }
        for signal in all_extracted_signals:
            key = signal_key(signal)
            previous = existing_signals.get(key)
            # A reviewed signal only returns when a genuinely new evidence key is
            # supplied. Contradictory and older evidence remain separate signals.
            if previous and previous.status in {"confirmed", "rejected"}:
                continue
            if previous and previous.confidence >= signal.confidence:
                continue
            existing_signals[key] = signal
        updates["profile_signals"] = list(existing_signals.values())
        updates["unknown_fields"] = list(
            dict.fromkeys(
                [
                    *current.unknown_fields,
                    *result.unknown_fields,
                    *extracted.unknown_fields,
                ]
            )
        )
        updates["profile_review_status"] = "draft"
        updates["id"] = current.id
        updates["code"] = current.code
        return current.model_copy(update=updates)
