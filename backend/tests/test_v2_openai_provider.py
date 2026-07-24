from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    AIProviderConfigurationError,
    AIProviderUnavailableError,
)
from app.integrations.ai_provider import get_v2_ai_provider
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.integrations.openai_provider import OpenAIV2AIProvider
from app.schemas.v2_dto import (
    LearnerProfile,
    LearnerRecord,
    AIQuestion,
    LessonDesignDraft,
    LessonDesignDraftDto,
    LessonPlanningResult,
    ProfileExtractionResult,
)
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories


class _FakeResponses:
    def __init__(self, content: str) -> None:
        self.content = content
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_text=self.content)


def _fake_client(content: str):
    return SimpleNamespace(responses=_FakeResponses(content))


class _FakeParsedResponses:
    def __init__(self) -> None:
        self.text_format = None
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        self.text_format = kwargs["text_format"]
        return SimpleNamespace(
            output_parsed=ProfileExtractionResult(
                learner=LearnerProfile(
                    id="a102",
                    code="Learner A-102",
                    age=7,
                    communicationMode="Short phrases",
                ),
                profileSignals=[],
                unknownFields=[],
                insights=["Use visual supports"],
            )
        )


class _FakePlanningResponses:
    def __init__(self) -> None:
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            output_parsed=LessonPlanningResult(
                questions=[
                    AIQuestion(
                        id="counting-range",
                        prompt="What counting range should the lesson target?",
                        field="goalText",
                        inputType="single_select",
                        options=[
                            {
                                "id": "one-to-five",
                                "label": "1 to 5",
                                "value": "Count from 1 to 5",
                            }
                        ],
                        selectedOptionIds=["one-to-five"],
                        required=True,
                    )
                ],
                draft=LessonDesignDraft(
                    id="generated-draft",
                    learnerId="a102",
                    goalText="Learner will count objects from 1 to 5.",
                    responseLevel="Point and count",
                    selectedMaterials=["Visual Cards"],
                ),
            )
        )


class _FakeImages:
    def __init__(self, image_base64: str) -> None:
        self.image_base64 = image_base64
        self.last_request = None

    def generate(self, **kwargs):
        self.last_request = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=self.image_base64, url=None)]
        )


def _fake_image_client(image_base64: str):
    images = _FakeImages(image_base64)
    return SimpleNamespace(images=images), images


def test_openai_provider_is_selected_without_eager_key_validation():
    config = Settings(_env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY=None)

    provider = get_v2_ai_provider(config)

    assert isinstance(provider, OpenAIV2AIProvider)


def test_openai_provider_requires_key_only_when_request_is_attempted():
    config = Settings(_env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY=None)
    provider = OpenAIV2AIProvider(config)

    with pytest.raises(
        RuntimeError,
        match=r"OPENAI_API_KEY is not configured\. Add it to backend/\.env\.local or your backend environment\.",
    ):
        provider.generate_lesson_package(
            LessonDesignDraftDto(
                id="draft-test",
                learnerId="a102",
                goalText="",
                responseLevel="",
                theme="",
                duration="",
                customNotes="",
            )
        )


def test_malformed_openai_output_uses_deterministic_mock_fallback():
    config = Settings(
        _env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY="not-a-real-key"
    )
    provider = OpenAIV2AIProvider(config, client=_fake_client("not-json"))
    learner = LearnerProfile(id="a102", code="Learner A-102", age=7)

    questions, draft = provider.generate_lesson_questions(
        learner, "I want to teach asking for help."
    )

    assert questions
    assert provider.last_fallback_used is True
    assert draft.learner_id == "a102"
    assert draft.goal_text == "Learner will ask for help using a short phrase."


def test_profile_extraction_uses_typed_responses_parse():
    config = Settings(
        _env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY="not-a-real-key"
    )
    responses = _FakeParsedResponses()
    provider = OpenAIV2AIProvider(
        config, client=SimpleNamespace(responses=responses)
    )
    learner = LearnerProfile(id="a102", code="Learner A-102", age=7)
    record = LearnerRecord(
        id="record-1",
        learnerId="a102",
        fileName="synthetic.txt",
        fileType="TXT",
        status="ready",
        uploadedAt="2026-07-23T00:00:00Z",
        extractedText="Synthetic classroom note.",
    )

    result = provider.extract_profile(learner, [record])

    assert responses.text_format is ProfileExtractionResult
    assert responses.request["model"] == "gpt-4.1-mini"
    assert "reasoning" not in responses.request
    assert result.learner.communication_mode == "Short phrases"
    assert result.insights == ["Use visual supports"]
    assert provider.last_fallback_used is False
    assert provider.last_generation_metadata.model == "gpt-4.1-mini"


def test_gpt5_requests_use_configured_low_reasoning_effort():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="not-a-real-key",
        OPENAI_REASONING_EFFORT="low",
    )
    responses = _FakeResponses('{"lessonBrief":"A concise lesson brief."}')
    provider = OpenAIV2AIProvider(
        config, client=SimpleNamespace(responses=responses)
    )

    result = provider.polish_lesson_brief(
        LessonDesignDraft(
            id="draft-test",
            learnerId="a102",
            goalText="Ask for help.",
            responseLevel="Short phrase",
            theme="Vehicles",
            duration="10 minutes",
            customNotes="",
        )
    )

    assert result == "A concise lesson brief."
    assert responses.request["model"] == "gpt-5.5"
    assert responses.request["reasoning"] == {"effort": "low"}


def test_lesson_package_uses_fast_dedicated_model_without_reasoning_controls():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="not-a-real-key",
        OPENAI_TEXT_MODEL="gpt-5.5",
        OPENAI_PACKAGE_MODEL="gpt-4.1-mini",
        OPENAI_PACKAGE_TIMEOUT_SECONDS=45,
    )
    responses = _FakeResponses(
        '{"lessonBrief":"Practice counting with brief teacher support.",'
        '"summaryTemplate":"Record independence and prompt level."}'
    )
    provider = OpenAIV2AIProvider(
        config, client=SimpleNamespace(responses=responses)
    )

    generated = provider.generate_lesson_package(
        LessonDesignDraftDto(
            id="draft-counting",
            learnerId="a102",
            goalText="The learner will count from 1 to 5.",
            responseLevel="Verbal counting",
            scenarios=["Count five classroom objects"],
            selectedMaterials=["Number cards 1 to 5"],
            theme="Counting",
            duration="5 minutes",
            customNotes="Use short directions.",
        )
    )

    assert generated["lessonBrief"].startswith("Practice counting")
    assert responses.request["model"] == "gpt-4.1-mini"
    assert "reasoning" not in responses.request
    assert provider.last_generation_metadata.model == "gpt-4.1-mini"


def test_lesson_planning_accepts_dynamic_question_ids_and_uses_fast_model():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="not-a-real-key",
        OPENAI_PLANNING_MODEL="gpt-4.1-mini",
    )
    responses = _FakePlanningResponses()
    provider = OpenAIV2AIProvider(
        config, client=SimpleNamespace(responses=responses)
    )

    questions, draft = provider.generate_lesson_questions(
        LearnerProfile(id="a102", code="Learner A-102", age=7),
        "I want to teach counting numbers.",
    )

    assert questions[0].id == "counting-range"
    assert draft.goal_text == "Learner will count objects from 1 to 5."
    assert responses.request["model"] == "gpt-4.1-mini"


def test_fail_closed_mode_never_returns_realistic_mock_content():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        AI_FAILURE_MODE="fail_closed",
        OPENAI_API_KEY="not-a-real-key",
    )
    provider = OpenAIV2AIProvider(config, client=_fake_client("not-json"))
    learner = LearnerProfile(id="a102", code="Learner A-102", age=7)

    with pytest.raises(
        AIProviderUnavailableError,
        match="AI generation is temporarily unavailable",
    ):
        provider.generate_lesson_questions(learner, "I want to teach asking for help.")

    assert provider.last_fallback_used is False


def test_unknown_provider_has_clear_configuration_error():
    config = Settings(_env_file=None).model_copy(update={"AI_PROVIDER": "other"})

    with pytest.raises(RuntimeError, match="Unsupported AI_PROVIDER: other"):
        get_v2_ai_provider(config)


def test_mock_provider_remains_the_default():
    config = Settings(_env_file=None)

    assert isinstance(get_v2_ai_provider(config), MockV2AIProvider)


def test_main_chat_flow_returns_safe_configuration_error_for_missing_key():
    config = Settings(_env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY=None)
    repos = V2Repositories()
    service = V2LessonChatService(repos, ai=OpenAIV2AIProvider(config))
    chat = service.start("a102")

    with pytest.raises(
        AIProviderConfigurationError,
        match=r"OPENAI_API_KEY is not configured\.",
    ):
        service.submit_request(chat.conversation_id, "Teach asking for help")


def test_main_package_pipeline_keeps_safety_checks_after_openai_fallback():
    config = Settings(
        _env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY="not-a-real-key"
    )
    provider = OpenAIV2AIProvider(config, client=_fake_client("malformed"))
    service = V2LessonPackageService(V2Repositories(), ai=provider)
    draft = LessonDesignDraftDto(
        id="draft-a102",
        learnerId="a102",
        goalText="Learner will ask for help using a short phrase.",
        responseLevel="Short phrase",
        scenarios=["Toy car stuck", "Closed box"],
        selectedMaterials=["Visual Cards", "Help Card", "Token Board"],
        theme="Vehicles",
        duration="10–12 min",
        customNotes="Use a visual prompt first.",
    )

    package = service.generate_product(draft)

    assert provider.last_fallback_used is True
    assert package.lessonBrief
    assert package.teachingFlow
    assert package.materials
    assert package.safetyReview is not None
    assert package.standardsChecks


def test_openai_material_image_uses_configured_image_model():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="not-a-real-key",
        OPENAI_IMAGE_MODEL="gpt-image-2",
    )
    client, images = _fake_image_client("aW1hZ2UtYnl0ZXM=")
    provider = OpenAIV2AIProvider(config, client=client)
    learner = LearnerProfile(id="a102", code="Learner A-102", age=7)

    generated = provider.generate_material_image(
        learner,
        "visual_card",
        "A toy car is stuck and a child asks for help.",
        "clean printable educational illustration",
        "1024x1024",
    )

    assert generated["status"] == "ready"
    assert generated["imageBase64"] == "aW1hZ2UtYnl0ZXM="
    assert generated["fallbackUsed"] is False
    assert images.last_request["model"] == "gpt-image-2"
    assert images.last_request["size"] == "1024x1024"


def test_openai_material_image_falls_back_when_output_is_unusable():
    config = Settings(
        _env_file=None, AI_PROVIDER="openai", OPENAI_API_KEY="not-a-real-key"
    )
    client, _ = _fake_image_client("")
    provider = OpenAIV2AIProvider(config, client=client)
    learner = LearnerProfile(id="a102", code="Learner A-102", age=7)

    generated = provider.generate_material_image(
        learner, "visual_card", "A teacher-reviewed classroom visual."
    )

    assert generated["status"] == "mock"
    assert generated["fallbackUsed"] is True
    assert provider.last_fallback_used is True
