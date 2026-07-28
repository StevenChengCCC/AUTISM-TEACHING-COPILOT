from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.core.exceptions import AIProviderUnavailableError, ValidationError
from app.schemas.v2_dto import (
    LearnerProfile,
    LearnerProfileExtractionDto,
    GenerationStatus,
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

    def extract(
        self, learner_id: str, *, force: bool = False
    ) -> LearnerProfileExtractionDto:
        learner = self.learners.get(learner_id)
        records = self.records.list_for_learner(learner_id)
        eligible_records = [
            record
            for record in records
            if record.status in {"ready", "reviewed"} and record.effective_text.strip()
        ]
        if (
            not force
            and getattr(self.learners.repos, "is_durable", False)
            and (
            learner.profile_review_status in {"reviewed", "confirmed"}
            or learner.profile_signals
            )
        ):
            return self._current_extraction(learner, records, len(eligible_records))
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
        try:
            provider_result = self.ai.extract_profile(learner, records_for_ai)
        except AIProviderUnavailableError:
            # A saved learner profile remains useful when the optional AI
            # enrichment provider is temporarily unavailable.  Do not replace
            # it with realistic mock claims and do not turn a read page into a
            # blocking 503.
            return self._current_extraction(
                learner,
                records,
                len(eligible_records),
                generation_status="provider_failure",
            )
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
            insights=self._build_review_insights(saved),
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

    def _current_extraction(
        self,
        learner: LearnerProfile,
        records: list,
        analyzed_record_count: int,
        generation_status: GenerationStatus | None = None,
    ) -> LearnerProfileExtractionDto:
        insights = self._build_review_insights(learner)
        return LearnerProfileExtractionDto(
            learner=self.learners.to_dto(learner),
            records=[self.records.to_dto(record) for record in records],
            insights=insights,
            profileSignals=learner.profile_signals,
            unknownFields=learner.unknown_fields,
            analyzedRecordCount=analyzed_record_count,
            status="complete",
            generationStatus=generation_status,
        )

    @staticmethod
    def _build_review_insights(learner: LearnerProfile) -> list[str]:
        """Create concise, evidence-cautious notes instead of repeating AI claims."""

        notes: list[str] = []

        def add(prefix: str, value: str) -> None:
            clean = " ".join(value.split()).strip(" .")
            replacements = {
                "approaching mastery": "showing documented progress",
                "Approaching mastery": "Showing documented progress",
                "mastery": "documented performance",
                "Mastery": "Documented performance",
                "critical": "potentially useful",
                "Critical": "Potentially useful",
                "essential": "potentially useful",
                "Essential": "Potentially useful",
            }
            for source, target in replacements.items():
                clean = clean.replace(source, target)
            if clean:
                notes.append(f"{prefix}: {clean}. Teacher confirmation is required.")

        if learner.strengths:
            add("Record suggests a relative strength", learner.strengths[0])
        if learner.emerging_skills:
            add("Record identifies an emerging skill", learner.emerging_skills[0])
        if learner.communication_mode:
            add("Record notes a communication mode", learner.communication_mode)
        for support in learner.support_needs[:2]:
            add("Record indicates this support may be useful", support)
        if learner.reinforcement_preferences and len(notes) < 4:
            add(
                "Record identifies a possible engagement support",
                learner.reinforcement_preferences[0],
            )
        if not notes:
            notes.append(
                "Saved learner information is ready for teacher review; unsupported details remain unknown."
            )
        return notes[:4]

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
        # Draft ages are unconfirmed. This also repairs legacy drafts created
        # when the frontend incorrectly prefilled every new learner as age 7.
        # Once a teacher confirms a profile, re-extraction cannot replace age.
        updates["age"] = (
            extracted.age
            if current.profile_review_status == "draft"
            else (current.age if current.age > 0 else extracted.age)
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
