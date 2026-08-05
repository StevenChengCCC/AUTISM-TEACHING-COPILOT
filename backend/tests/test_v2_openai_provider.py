import json
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    AIProviderConfigurationError,
    AIProviderUnavailableError,
)
from app.integrations.ai_provider import get_v2_ai_provider
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.integrations.openai_provider import (
    OpenAIV2AIProvider,
    _LessonPlanningTransport,
    _LessonPackageCopyTransport,
)
from app.schemas.v2_dto import (
    CanonicalLearnerProfile,
    LearnerProfile,
    LearnerRecord,
    AIQuestion,
    LessonDesignDraft,
    LessonDesignDraftDto,
    LessonSpec,
    LessonSpecGoal,
    LessonSpecMaterialRequest,
    LessonSuccessCriterion,
    InstructionalConstraintSnapshot,
    ProfileExtractionResult,
    ProfileFactor,
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


def _valid_package_lesson_spec() -> LessonSpec:
    requests = [
        LessonSpecMaterialRequest(
            requestId=f"request-{material_type}",
            materialType=material_type,
            displayLabel=label,
            instructionalPurpose="Support the confirmed break-request goal.",
        )
        for material_type, label in (
            ("break_card", "Break Card"),
            ("first_then_board", "First-Then Board"),
            ("data_sheet", "Data Sheet"),
        )
    ]
    return LessonSpec.model_construct(
        id="lesson-spec-package-copy",
        material_requests=requests,
    )


def _package_copy_response() -> str:
    steps = []
    for index, title in enumerate(("Prepare", "Practice", "Close"), start=1):
        steps.append(
            {
                "id": f"step-{index}",
                "title": title,
                "description": "Practice the current break-request goal.",
                "duration": "3 minutes",
                "teacherAction": "Create one natural opportunity and pause.",
                "learnerAction": "Request a break using speech or AAC.",
                "teacherScript": "You can ask for a break.",
                "expectedLearnerResponse": "Says or selects Break, please.",
                "waitTime": "5 seconds",
                "promptAction": "Use the least support needed, then fade.",
                "reinforcementAction": "Honor the break request.",
                "errorCorrectionAction": "Respond neutrally and offer another opportunity.",
                "dataToRecord": ["response mode", "prompt level"],
                "transitionCue": "Preview the next brief activity.",
                "breakOption": "Honor a communicated break or stop request.",
            }
        )
    return json.dumps(
        {
            "lessonBrief": "Practice a functional break request during familiar transitions.",
            "summaryTemplate": "Record independent and prompted break requests separately.",
            "teachingFlow": steps,
        }
    )


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
                    normalizedProfile=CanonicalLearnerProfile(
                        learnerId="a102",
                        age=7,
                        factors=[
                            ProfileFactor(
                                id="communication-short-phrases",
                                category="communication",
                                label="Short phrases",
                                value="Uses short phrases",
                                status="confirmed_current",
                                confidence=0.9,
                                sourceEvidence="Synthetic classroom note.",
                                sourceRecordId="record-1",
                                instructionalImplication="Accept short phrase responses.",
                            )
                        ],
                    ),
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
            output_parsed=kwargs["text_format"](
                questions=[
                    {
                        "id": "counting-range",
                        "prompt": "What counting range should the lesson target?",
                        "field": "goalText",
                        "inputType": "single_select",
                        "helperText": "Choose the observable target.",
                        "options": [
                            {
                                "id": "one-to-five",
                                "label": "1 to 5",
                                "value": "Count from 1 to 5",
                                "description": "A brief observable counting target.",
                                "recommended": True,
                                "reason": "Matches the teacher request.",
                                "profileFactorIds": [],
                                "assumptions": [],
                            }
                        ],
                        "allowCustomAnswer": True,
                        "maxSelections": 1,
                    }
                ],
                goalText="Learner will count objects from 1 to 5.",
                observableResponse="Points to and counts five objects.",
                responseLevel="Point and count",
                scenarios=["Small-group math"],
                selectedMaterials=["Visual Cards"],
                theme="Familiar classroom objects",
                duration="10 minutes",
                customNotes="Wait before prompting.",
            )
        )


class _SchemaRejectedPlanningResponses:
    def __init__(self) -> None:
        self.parse_calls = 0
        self.create_calls = 0

    def parse(self, **kwargs):
        self.parse_calls += 1
        error = RuntimeError("schema rejected")
        error.status_code = 400
        raise error

    def create(self, **kwargs):
        self.create_calls += 1
        value = {
            "questions": [
                {
                    "id": "break-request",
                    "prompt": "What should the learner practice?",
                    "helperText": "Choose the observable target.",
                    "field": "goalText",
                    "inputType": "single_select",
                    "options": [
                        {
                            "id": "break-please",
                            "label": "Break, please",
                            "value": "Request a break",
                            "description": "Speech or AAC are both accepted.",
                            "recommended": True,
                            "reason": "Matches the teacher request.",
                            "profileFactorIds": [],
                            "assumptions": [],
                        }
                    ],
                    "allowCustomAnswer": True,
                    "maxSelections": 1,
                }
            ],
            "goalText": "Request a break with speech or AAC.",
            "observableResponse": "Says or selects Break, please.",
            "responseLevel": "Speech or AAC",
            "scenarios": ["Table work"],
            "selectedMaterials": ["Break Card"],
            "theme": "Classroom transitions",
            "duration": "10 minutes",
            "customNotes": "Wait five seconds.",
        }
        return SimpleNamespace(output_text=__import__("json").dumps(value))


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
            LessonSpec.model_construct(id="lesson-spec-test")
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
    provider = OpenAIV2AIProvider(config, client=SimpleNamespace(responses=responses))
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
    assert "Extract every actionable" in responses.request["instructions"]
    assert "not_approved" in responses.request["instructions"]
    assert "generationConstraints" in responses.request["instructions"]
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
    provider = OpenAIV2AIProvider(config, client=SimpleNamespace(responses=responses))

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
    responses = _FakeResponses(_package_copy_response())
    provider = OpenAIV2AIProvider(config, client=SimpleNamespace(responses=responses))

    generated = provider.generate_lesson_package(_valid_package_lesson_spec())

    assert generated["lessonBrief"].startswith("Practice a functional")
    assert len(generated["teachingFlow"]) == 3
    assert {item["type"] for item in generated["materials"]}.issuperset(
        {"break_card", "first_then_board", "data_sheet"}
    )
    assert responses.request["model"] == "gpt-4.1-mini"
    assert "reasoning" not in responses.request
    assert provider.last_generation_metadata.model == "gpt-4.1-mini"


def test_lesson_package_provider_schema_has_no_open_ended_material_json():
    schema = _LessonPackageCopyTransport.model_json_schema()

    assert set(schema["properties"]) == {
        "lessonBrief",
        "summaryTemplate",
        "teachingFlow",
    }
    assert "materials" not in schema["properties"]
    assert "materialCopySuggestions" not in schema["properties"]
    assert schema["additionalProperties"] is False
    step_schema = schema["$defs"]["_TeachingStepCopyTransport"]
    assert step_schema["additionalProperties"] is False
    assert all(
        property_schema.get("additionalProperties") is not True
        for property_schema in step_schema["properties"].values()
    )


def test_lesson_package_does_not_repeat_full_opportunity_budget_across_steps():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="not-a-real-key",
        OPENAI_PACKAGE_MODEL="gpt-4.1-mini",
    )
    payload = json.loads(_package_copy_response())
    payload["teachingFlow"][0]["description"] = "Use five opportunities in guided practice."
    payload["teachingFlow"][1]["description"] = "Repeat five opportunities in another context."
    responses = _FakeResponses(json.dumps(payload))
    provider = OpenAIV2AIProvider(config, client=SimpleNamespace(responses=responses))
    lesson_spec = _valid_package_lesson_spec().model_copy(
        update={
            "goal": LessonSpecGoal(
                displayText="Request a break",
                observableBehavior="Say or select Break, please",
                successCriterion=LessonSuccessCriterion(
                    requiredSuccessfulOpportunities=4,
                    totalOpportunities=5,
                    requiredContexts=1,
                ),
            )
        }
    )

    generated = provider.generate_lesson_package(lesson_spec)
    descriptions = " ".join(step["description"] for step in generated["teachingFlow"])

    assert descriptions.casefold().count("five opportunities") == 1
    assert "the remaining planned opportunities" in descriptions


def test_lesson_planning_accepts_dynamic_question_ids_and_uses_fast_model():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="not-a-real-key",
        OPENAI_PLANNING_MODEL="gpt-4.1-mini",
    )
    responses = _FakePlanningResponses()
    provider = OpenAIV2AIProvider(config, client=SimpleNamespace(responses=responses))

    questions, draft = provider.generate_lesson_questions(
        LearnerProfile(id="a102", code="Learner A-102", age=7),
        "I want to teach counting numbers.",
    )

    assert questions[0].id == "counting-range"
    assert draft.goal_text == "Learner will count objects from 1 to 5."
    assert responses.request["model"] == "gpt-4.1-mini"
    payload = responses.request["input"]
    assert "instructionalConstraintSnapshot" in payload
    assert "profileRevision" in payload
    assert "unresolvedAssumptions" in payload
    assert "excludedItems" in payload
    assert "supportedMaterialCatalog" in payload
    assert "Learner A-102" not in payload


def test_lesson_planning_retries_schema_rejection_in_validated_json_mode():
    config = Settings(
        _env_file=None,
        AI_PROVIDER="openai",
        OPENAI_API_KEY="not-a-real-key",
        AI_FAILURE_MODE="fail_closed",
        OPENAI_PLANNING_MODEL="gpt-4.1-mini",
    )
    responses = _SchemaRejectedPlanningResponses()
    provider = OpenAIV2AIProvider(config, client=SimpleNamespace(responses=responses))

    questions, draft = provider.generate_lesson_questions(
        LearnerProfile(id="a102", code="Learner A-102", age=7),
        "Teach a functional break request.",
    )

    assert responses.parse_calls == 1
    assert responses.create_calls == 1
    assert questions[0].id == "break-request"
    assert draft.goal_text == "Request a break with speech or AAC."
    assert provider.last_fallback_used is False


def test_lesson_planning_prefers_reviewed_profile_contexts_over_generic_ai_settings():
    payload = json.loads(_SchemaRejectedPlanningResponses().create().output_text)
    payload["questions"].append(
        {
            "id": "generic-settings",
            "prompt": "Where will practice happen?",
            "helperText": "Choose a setting.",
            "field": "scenarios",
            "inputType": "multi_select",
            "options": [
                {
                    "id": "generic-classroom",
                    "label": "A classroom",
                    "value": "A classroom",
                    "description": "Generic provider suggestion.",
                    "recommended": True,
                    "reason": "Generic setting.",
                    "profileFactorIds": [],
                    "assumptions": [],
                }
            ],
            "allowCustomAnswer": True,
            "maxSelections": 3,
        }
    )
    planning = _LessonPlanningTransport.model_validate(payload)
    snapshot = InstructionalConstraintSnapshot(
        learnerId="synthetic-context-learner",
        profileRevision="profile-context-revision",
        generalization={
            "required": True,
            "contexts": [
                "transit-map activity to table work",
                "art activity to cleanup",
                "free choice to shared reading",
            ],
        },
        profileFactorIds=["three-contexts"],
    )

    questions, draft = OpenAIV2AIProvider._planning_transport_to_domain(
        planning,
        LearnerProfile(
            id="synthetic-context-learner",
            code="SYN-CONTEXT",
            age=11,
        ),
        "Teach a break request during familiar classroom transitions.",
        snapshot,
        ["Break Card", "First-Then Board", "Data Sheet"],
    )

    scenario_question = next(item for item in questions if item.field == "scenarios")
    expected = [
        "transit-map activity to table work",
        "art activity to cleanup",
        "free choice to shared reading",
    ]
    assert [item.value for item in scenario_question.options] == expected
    assert all(item.recommended for item in scenario_question.options)
    assert all(item.profile_factor_ids == ["three-contexts"] for item in scenario_question.options)
    assert draft.scenarios == expected


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
