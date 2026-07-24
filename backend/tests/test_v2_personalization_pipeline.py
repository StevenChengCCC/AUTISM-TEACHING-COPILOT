from base64 import b64encode
from datetime import datetime, timezone

from app.core.config import Settings
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.schemas.v2_dto import (
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraftDto,
    ProfileExtractionResult,
    ProfileSignal,
)
from app.services.v2_ai_context_service import (
    build_image_generation_context,
    build_lesson_generation_context,
)
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_profile_extraction_service import V2ProfileExtractionService
from app.services.v2_repositories import V2Repositories
from app.skills.models import GenerationMetadata


def _draft(
    learner_id: str,
    goal: str,
    *,
    theme: str = "",
    selected: list[str] | None = None,
) -> LessonDesignDraftDto:
    return LessonDesignDraftDto(
        id=f"draft-{learner_id}",
        learnerId=learner_id,
        goalText=goal,
        responseLevel="Short phrase",
        scenarios=["Sorting pencils"],
        selectedMaterials=selected or ["Visual Cards", "Data Sheet"],
        theme=theme,
        duration="10 min",
        customNotes="Wait before prompting.",
    )


def test_profile_extraction_saves_anonymous_record_signals_and_draft_status():
    repos = V2Repositories()
    repos.learners.save(LearnerProfile(id="anonymous", code="Learner DEMO", age=8))
    repos.records.save(
        LearnerRecord(
            id="record-anonymous",
            learner_id="anonymous",
            file_name="anonymous-notes.txt",
            file_type="TXT",
            status="ready",
            uploaded_at=datetime.now(timezone.utc),
            extracted_text=(
                "Higher engagement was observed during building block activities. "
                "The learner uses short phrases and benefits from visual support."
            ),
        )
    )

    result = V2ProfileExtractionService(repos, ai=MockV2AIProvider()).extract(
        "anonymous"
    )
    stored = repos.learners.get("anonymous")

    assert stored is not None
    assert stored.profile_review_status == "draft"
    assert any(
        signal.category == "interest" and signal.label == "Building blocks"
        for signal in stored.profile_signals
    )
    assert result.learner.profileReviewStatus == "draft"
    assert result.profileSignals == stored.profile_signals


class _ConflictingExtractionProvider(MockV2AIProvider):
    def extract_profile(self, learner, records):
        extracted = learner.model_copy(
            update={
                "interests": ["Trains"],
                "communication_mode": "Full sentences",
            }
        )
        return ProfileExtractionResult(
            learner=extracted,
            profileSignals=[
                ProfileSignal(
                    id="new-interest",
                    category="interest",
                    label="Trains",
                    confidence=0.91,
                    status="suggested",
                    evidence="A record directly mentions train activities.",
                    sourceRecordId=None,
                )
            ],
            unknownFields=[],
            insights=["Review the new suggestion."],
        )


def test_confirmed_teacher_values_and_signal_decisions_are_not_overwritten():
    repos = V2Repositories()
    confirmed = ProfileSignal(
        id="confirmed-art",
        category="interest",
        label="Art",
        confidence=1,
        status="confirmed",
        evidence="Teacher confirmed.",
    )
    rejected = ProfileSignal(
        id="rejected-trains",
        category="interest",
        label="Trains",
        confidence=0.5,
        status="rejected",
        evidence="Teacher rejected this suggestion.",
    )
    repos.learners.save(
        LearnerProfile(
            id="teacher-profile",
            code="Learner T-1",
            age=8,
            interests=["Art"],
            communication_mode="AAC",
            profile_signals=[confirmed, rejected],
            profile_review_status="confirmed",
        )
    )

    V2ProfileExtractionService(repos, ai=_ConflictingExtractionProvider()).extract(
        "teacher-profile"
    )
    stored = repos.learners.get("teacher-profile")

    assert stored is not None
    assert stored.interests == ["Art"]
    assert stored.communication_mode == "AAC"
    assert (
        next(
            signal for signal in stored.profile_signals if signal.label == "Trains"
        ).status
        == "rejected"
    )


def test_missing_interest_uses_neutral_context_and_profile_aware_mock_content():
    repos = V2Repositories()
    learner = LearnerProfile(
        id="neutral",
        code="Learner N-0",
        age=8,
        communication_mode="Gestures",
        support_needs=["Visual choices"],
        profile_review_status="confirmed",
    )
    repos.learners.save(learner)
    draft = _draft("neutral", "Learner will choose a classroom item.")

    image_context = build_image_generation_context(
        learner, "visual_card", "choosing a classroom item"
    )
    package = V2LessonPackageService(repos, ai=MockV2AIProvider()).generate_product(
        draft
    )

    assert image_context["neutralFallbackTheme"] is True
    assert image_context["interestTheme"] is None
    assert "neutral classroom" in package.lessonBrief.lower()
    assert "vehicle" not in package.lessonBrief.lower()
    assert "neutral classroom" in package.materials[0].content["imagePrompt"].lower()


class _RecordingPackageProvider(MockV2AIProvider):
    provider_name = "recording"

    def __init__(self):
        self.context = None

    def generate_lesson_package(self, draft, learner_context=None):
        self.context = learner_context
        return {
            "lessonBrief": "Custom profile-aware brief.",
            "summaryTemplate": "Custom reflection.",
            "teachingFlow": [
                {
                    "id": "custom-step",
                    "title": "Custom generated step",
                    "description": "Uses the confirmed profile context.",
                    "duration": "3 min",
                    "teacherAction": "Offer a visual choice.",
                    "learnerAction": "Selects an option.",
                }
            ],
            "materials": [
                {
                    "type": "visual_card",
                    "title": "Custom Pencil Choice",
                    "content": {"phrase": "My choice"},
                    "imageConcept": "choosing pencils at a classroom table",
                    "imagePrompt": "Show a simple pencil choice.",
                    "imageAltText": "A pencil choice.",
                }
            ],
        }


def test_package_provider_receives_safe_context_and_generated_content_is_used():
    repos = V2Repositories()
    provider = _RecordingPackageProvider()
    package = V2LessonPackageService(repos, ai=provider).generate_product(
        _draft("b214", "Learner will choose a break option.", theme="Music")
    )

    assert provider.context is not None
    assert provider.context["communicationMode"].startswith("AAC")
    assert "learnerCode" not in provider.context
    assert package.teachingFlow[0].title == "Custom generated step"
    visual = next(item for item in package.materials if item.type == "visual_card")
    assert visual.title == "Custom Pencil Choice"
    assert visual.content["phrase"] == "My choice"
    assert package.aiProvider == "recording"
    assert package.fallbackUsed is True


class _IncompleteStructuredPackageProvider(_RecordingPackageProvider):
    provider_name = "openai"

    def __init__(self):
        super().__init__()
        self.generation_metadata_by_skill = {}
        self.last_generation_metadata = GenerationMetadata(
            status="ready",
            provider="openai",
            model="gpt-5.5",
            skillId="lesson_generation",
            skillVersion="v1",
            promptTemplateVersion="v1",
            inputSchemaVersion="v1",
            outputSchemaVersion="v1",
            evaluatorVersion="v1",
            generatedAt=datetime.now(timezone.utc).isoformat(),
            outputSource="provider",
            teacherReviewRequired=True,
        )

    def generate_lesson_package(self, draft, learner_context=None):
        self.context = learner_context
        return {
            "lessonBrief": "Use short counting practice with teacher support.",
            "summaryTemplate": "Record the response and prompt level.",
            "teachingFlow": [{"title": "Incomplete provider step"}],
            "materials": [],
        }


def test_incomplete_provider_structure_uses_safe_templates_for_custom_materials():
    repos = V2Repositories()
    provider = _IncompleteStructuredPackageProvider()

    package = V2LessonPackageService(repos, ai=provider).generate_product(
        _draft(
            "a102",
            "The learner will verbally count from 1 to 5 in order.",
            theme="Counting and number sequencing",
            selected=["Number cards 1 to 5", "iPad token board app"],
        )
    )

    assert package.lessonBrief == (
        "Use short counting practice with teacher support."
    )
    assert package.fallbackUsed is True
    assert len(package.teachingFlow) == 5
    assert {item.type for item in package.materials} == {
        "visual_card",
        "token_board",
        "summary_template",
    }


class _CapturingImageProvider(_RecordingPackageProvider):
    def __init__(self):
        super().__init__()
        self.image_prompts = []

    def generate_lesson_package(self, draft, learner_context=None):
        generated = super().generate_lesson_package(draft, learner_context)
        generated["materials"][0].update(
            {
                "imageConcept": f"{draft.goalText} with art supplies",
                "imagePrompt": "Include Learner SECRET and raw-record-private-text.",
            }
        )
        return generated

    def generate_material_image(
        self, learner, material_type, prompt, style=None, size=None
    ):
        self.image_prompts.append(prompt)
        return {
            "imageId": "captured-image",
            "status": "ready",
            "imageUrl": None,
            "imageBase64": b64encode(b"image").decode(),
            "promptUsed": prompt,
            "fallbackUsed": False,
        }


def test_image_prompt_uses_confirmed_interest_without_identifiers_or_record_text(
    tmp_path,
):
    repos = V2Repositories()
    repos.learners.save(
        LearnerProfile(
            id="secret-id",
            code="Learner SECRET",
            age=8,
            interests=["Art"],
            communication_mode="Short phrases",
            notes="raw-record-private-text",
            profile_review_status="confirmed",
        )
    )
    provider = _CapturingImageProvider()
    images = V2ImageAssetService(
        repos,
        external_providers=[],
        ai=provider,
        config=Settings(
            _env_file=None,
            IMAGE_ASSET_STRATEGY="generate_first",
            STORAGE_DIR=str(tmp_path),
        ),
    )

    package_service = V2LessonPackageService(repos, ai=provider, images=images)
    package = package_service.generate_product(
        _draft("secret-id", "Learner SECRET will sort pencils.", theme="Art")
    )
    package_service.queue_product_images(package.id)
    package_service.prepare_product_images(package.id)
    package = package_service.get_product(package.id)
    prompt = provider.image_prompts[0]

    assert "Art" in prompt
    assert "Learner SECRET" not in prompt
    assert "secret-id" not in prompt
    assert "raw-record-private-text" not in prompt
    assert package.materials[0].content["imageSafetyStatus"] == "needs_review"


def test_unrelated_profile_never_receives_vehicle_default():
    repos = V2Repositories()
    draft = _draft(
        "c087", "Learner will identify an emotion from two pictures.", theme="Emotions"
    )
    package = V2LessonPackageService(repos, ai=MockV2AIProvider()).generate_product(
        draft
    )
    rendered = " ".join(
        [
            package.lessonBrief,
            *[
                str(material.content.get("imagePrompt", ""))
                for material in package.materials
            ],
        ]
    ).lower()

    assert "vehicle" not in rendered
    assert "toy car" not in rendered
    assert "emotion" in rendered


class _FailingPackageProvider(MockV2AIProvider):
    provider_name = "failing-test-provider"

    def generate_lesson_package(self, draft, learner_context=None):
        raise RuntimeError("provider unavailable")


def test_package_generation_succeeds_with_profile_aware_fallback():
    repos = V2Repositories()
    package = V2LessonPackageService(
        repos, ai=_FailingPackageProvider()
    ).generate_product(
        _draft("b214", "Learner will request a break using AAC.", theme="Music")
    )

    assert package.fallbackUsed is True
    assert package.aiProvider == "failing-test-provider"
    assert "music" in package.lessonBrief.lower()
    assert package.materials
    assert package.safetyReview is not None


def test_lesson_context_contains_no_record_or_storage_metadata():
    repos = V2Repositories()
    learner = repos.learners.get("a102")
    assert learner is not None
    context = build_lesson_generation_context(
        learner, _draft("a102", "Learner will ask for help.", theme="Vehicles")
    )
    serialized = str(context)

    assert "IEP summary.pdf" not in serialized
    assert "record-a1" not in serialized
    assert "storage" not in serialized.lower()
