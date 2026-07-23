from fastapi.testclient import TestClient

from app.api.v2_routes import health
from app.core.config import settings as app_settings
from app.main import app
from app.schemas.v2_dto import (
    AIChatState,
    LessonDesignDraft,
    LessonDesignDraftDto,
    LessonPackageUpdateRequest,
    QuestionAnswerUpdate,
)
from app.services.v2_lesson_chat_service import V2LessonChatService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories
from app.services.v2_session_service import V2SessionService


def test_v2_health_contract():
    assert health().model_dump(by_alias=True) == {
        "status": "ok",
        "version": "v2-product",
        "environment": "development",
    }


def test_v2_development_ai_endpoints_are_safe_and_work_in_mock_mode():
    client = TestClient(app)

    status = client.get("/api/v2/dev/ai-status")
    assert status.status_code == 200
    assert status.json() == {
        "provider": "mock",
        "textModel": "gpt-5.5",
        "imageModel": "gpt-image-2",
        "hasApiKey": False,
    }

    questions = client.post(
        "/api/v2/dev/test-ai-lesson-questions",
        json={
            "learnerId": "a102",
            "message": "I want to teach asking for help.",
        },
    )
    assert questions.status_code == 200
    assert questions.json()["provider"] == "mock"
    assert questions.json()["fallbackUsed"] is False
    assert len(questions.json()["questions"]) > 5
    assert {item["field"] for item in questions.json()["questions"]} >= {
        "goalText",
        "baseline",
        "responseLevel",
        "scenarios",
        "selectedMaterials",
        "dataCollection",
    }

    package = client.post(
        "/api/v2/dev/test-ai-lesson-package",
        json={
            "learnerId": "a102",
            "goalText": "Learner will ask for help using a short phrase.",
            "responseLevel": "Short phrase",
            "scenarios": ["Toy car stuck", "Closed box"],
            "selectedMaterials": [
                "Visual Cards",
                "Help Card",
                "Token Board",
                "Data Sheet",
                "Summary Template",
            ],
            "theme": "Vehicles",
            "duration": "10–12 min",
            "customNotes": "Use visual prompt first and token board reinforcement.",
        },
    )
    assert package.status_code == 200
    assert package.json()["fallbackUsed"] is False
    assert package.json()["generatedContent"]["lessonBrief"]

    image = client.post(
        "/api/v2/dev/test-image-generation",
        json={
            "learnerId": "a102",
            "materialType": "visual_card",
            "prompt": (
                "A simple classroom visual card showing a toy car stuck and a "
                "child asking for help."
            ),
            "style": "clean printable educational illustration",
            "size": "1024x1024",
        },
    )
    assert image.status_code == 200
    assert image.json()["status"] == "mock"
    assert image.json()["provider"] == "mock"
    assert image.json()["model"] == "gpt-image-2"
    assert image.json()["fallbackUsed"] is False
    assert "promptUsed" in image.json()
    assert "apiKey" not in image.text


def test_main_chat_http_flow_returns_clear_503_when_openai_key_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(app_settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(app_settings, "OPENAI_API_KEY", None)
    client = TestClient(app)
    initial = client.post("/api/v2/lesson-chat/start", json={"learnerId": "a102"})

    response = client.post(
        "/api/v2/lesson-chat/message",
        json={
            "conversationId": initial.json()["conversationId"],
            "learnerId": "a102",
            "message": "I want to teach asking for help.",
            "currentDraft": initial.json()["draft"],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "OPENAI_API_KEY is not configured. Add it to backend/.env.local "
        "or your backend environment."
    )
    assert response.json()["code"] == "ai_provider_not_configured"
    assert response.json()["retryable"] is False
    assert response.json()["requestId"] == response.headers["X-Request-ID"]


def test_v2_chat_is_input_driven_and_uses_camel_case_contracts():
    repos = V2Repositories()
    service = V2LessonChatService(repos)

    initial = service.start("a102")
    assert initial.questions == []
    assert initial.can_generate is False

    chat = service.submit_request(
        initial.conversation_id, "I want to teach Learner A-102 to ask for help."
    )
    assert len(chat.questions) > 5
    assert chat.can_generate is False
    assert chat.draft.selected_materials == [
        "Visual Cards",
        "Help Card",
        "Token Board",
        "Data Sheet",
        "Summary Template",
    ]
    payload = chat.model_dump(mode="json", by_alias=True)
    assert "conversationId" in payload
    assert "selectedMaterials" in payload["draft"]

    updated = service.update_answer(
        chat.conversation_id,
        "response-level",
        QuestionAnswerUpdate(selected_option_ids=[], custom_answer="Two-word request"),
    )
    response_question = next(
        question for question in updated.questions if question.id == "response-level"
    )
    custom = response_question.options[-1]
    assert custom.source == "teacher_custom"
    assert updated.draft.response_level == "Two-word request"


def test_v2_package_runs_safety_and_standards_before_persistence():
    repos = V2Repositories()
    chat_service = V2LessonChatService(repos)
    chat = chat_service.start("a102")
    chat = chat_service.submit_request(chat.conversation_id, "Practice asking for help")

    package = V2LessonPackageService(repos).generate(chat.draft)

    assert package.safety_report.passed is True
    assert package.safety_report.checks
    assert package.standards_report.checks
    assert repos.packages.get(package.id) is not None
    assert repos.materials.for_package(package.id)


def test_lesson_package_document_update_preserves_materials_and_quality_data():
    repos = V2Repositories()
    chat_service = V2LessonChatService(repos)
    chat = chat_service.start("a102")
    chat = chat_service.submit_request(chat.conversation_id, "Practice asking for help")
    service = V2LessonPackageService(repos)
    package = service.generate_product(
        LessonDesignDraftDto.model_validate(
            chat.draft.model_dump(mode="json", by_alias=True)
        )
    )
    original_materials = [
        material.model_dump(mode="json", by_alias=True)
        for material in package.materials
    ]
    updated_flow = [
        package.teachingFlow[0].model_copy(
            update={"description": "Teacher-edited warm-up description."}
        ),
        *package.teachingFlow[1:],
    ]

    updated = service.update_product(
        package.id,
        LessonPackageUpdateRequest(
            lessonBrief="Teacher-edited lesson brief.",
            summaryTemplate="Teacher-edited summary template.",
            teachingFlow=updated_flow,
            documentContent={
                "title": "Asking for Help Lesson Kit",
                "promptingPlan": "Wait five seconds before adding a prompt.",
            },
        ),
    )

    assert updated.lessonBrief == "Teacher-edited lesson brief."
    assert updated.summaryTemplate == "Teacher-edited summary template."
    assert updated.teachingFlow[0].description == "Teacher-edited warm-up description."
    assert updated.documentContent["promptingPlan"].startswith("Wait five")
    assert [
        material.model_dump(mode="json", by_alias=True)
        for material in updated.materials
    ] == original_materials
    assert updated.safetyReview == package.safetyReview
    assert updated.standardsChecks == package.standardsChecks


def test_v2_repository_seed_is_deterministic_and_multidimensional():
    repos = V2Repositories()

    learner = repos.learners.get("a102")
    assert learner is not None
    assert learner.tags == ["Visual support", "Short attention span", "Asking for Help"]
    assert learner.reinforcement_preferences == ["Token board", "Car play", "Praise"]
    assert len(repos.materials_library.list()) == 7
    assert {session.status for session in repos.sessions.list()} == {
        "planned",
        "in_progress",
        "completed",
        "draft",
    }

    points = repos.progress_data.list()
    assert [point.accuracyPercent for point in points] == [52, 55, 53, 56, 54, 58]
    assert points[0].promptLevel == "Level 3"
    assert points[-1].promptLevel == "Level 2"
    assert {
        "engagement",
        "prompt_fading",
        "generalization",
        "regulation_recovery",
        "participation",
        "independence",
    } <= {signal.type for signal in repos.progress_signals.list()}


def test_v2_repository_can_create_read_and_update_conversations():
    repos = V2Repositories()
    conversation = AIChatState(
        conversation_id="conversation-test",
        learner_id="a102",
        draft=LessonDesignDraft(id="draft-test", learner_id="a102"),
    )

    repos.conversations.create(conversation)
    conversation.can_generate = True
    repos.conversations.update(conversation)

    stored = repos.conversations.get("conversation-test")
    assert stored is not None
    assert stored.can_generate is True


def test_v2_learner_record_and_extraction_http_contracts():
    client = TestClient(app)

    learner = client.get("/api/v2/learners/a102")
    assert learner.status_code == 200
    assert learner.json()["tags"] == [
        "Visual support",
        "Short attention span",
        "Asking for Help",
    ]
    assert "supportNeeds" in learner.json()
    assert "support_needs" not in learner.json()
    assert client.get("/api/v2/learners/does-not-exist").status_code == 404

    created = client.post(
        "/api/v2/learners",
        json={
            "code": "Learner API-TEST",
            "age": 8,
            "tags": ["New"],
            "interests": ["Art"],
            "supportNeeds": ["Visual support"],
            "reinforcementPreferences": ["Praise"],
            "communicationMode": "Short phrases",
            "attentionProfile": "Short activities.",
            "notes": "Draft learner.",
        },
    )
    assert created.status_code == 201
    learner_id = created.json()["id"]

    updated = client.patch(
        f"/api/v2/learners/{learner_id}",
        json={"notes": "Teacher confirmed."},
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Teacher confirmed."

    record = client.post(
        f"/api/v2/learners/{learner_id}/records",
        json={
            "fileName": "Session notes.txt",
            "fileType": "TXT",
            "text": "Uses a visual cue.",
        },
    )
    assert record.status_code == 201
    assert record.json()["extractedText"] == "Uses a visual cue."
    assert record.json()["learnerId"] == learner_id

    extraction = client.get("/api/v2/learners/n501/profile-extraction")
    assert extraction.status_code == 200
    assert extraction.json()["insights"] == [
        "Use visual supports",
        "Keep activities short",
        "Add multiple examples",
    ]
    assert extraction.json()["analyzedRecordCount"] == 5
    assert extraction.json()["status"] == "complete"


def test_v2_lesson_chat_product_http_flow():
    client = TestClient(app)

    started = client.post("/api/v2/lesson-chat/start", json={"learnerId": "a102"})
    assert started.status_code == 201
    state = started.json()
    assert state["conversationId"] == "conversation-a102"
    assert state["questions"] == []
    assert state["canGenerate"] is False
    assert [message["role"] for message in state["messages"]] == ["assistant"]

    generated = client.post(
        "/api/v2/lesson-chat/message",
        json={
            "conversationId": state["conversationId"],
            "learnerId": "a102",
            "message": "I want to teach Learner A-102 to ask for help.",
            "currentDraft": {},
        },
    )
    assert generated.status_code == 200
    state = generated.json()
    assert {question["field"] for question in state["questions"]} >= {
        "goalText",
        "baseline",
        "responseLevel",
        "scenarios",
        "opportunities",
        "duration",
        "promptingStart",
        "promptingLimits",
        "reinforcementPlan",
        "errorCorrection",
        "selectedMaterials",
        "dataCollection",
        "generalizationPlan",
        "teacherConstraints",
    }
    assert state["draft"]["goalText"] == (
        "Learner will ask for help using a short phrase."
    )
    assert state["draft"]["theme"] == "Vehicles"
    assert state["draft"]["scenarios"] == [
        "Toy car stuck",
        "Closed box",
        "Backpack zipper",
    ]
    assert "Car play" in state["draft"]["customNotes"]
    assert "Visual prompt first" in state["draft"]["customNotes"]

    resumed = client.post(
        "/api/v2/lesson-chat/start",
        json={"learnerId": "a102", "resumeExisting": True},
    )
    assert resumed.status_code == 201
    assert resumed.json()["questions"]
    assert resumed.json()["draft"]["goalText"] == state["draft"]["goalText"]

    fresh = client.post(
        "/api/v2/lesson-chat/start",
        json={"learnerId": "a102", "resumeExisting": False},
    )
    assert fresh.status_code == 201
    assert fresh.json()["questions"] == []
    state = client.post(
        "/api/v2/lesson-chat/message",
        json={
            "conversationId": fresh.json()["conversationId"],
            "learnerId": "a102",
            "message": "I want to teach Learner A-102 to ask for help.",
        },
    ).json()

    custom = client.patch(
        f"/api/v2/lesson-chat/{state['conversationId']}/answers",
        json={
            "questionId": "scenarios",
            "selectedOptionIds": ["toy-car"],
            "customAnswer": "Snack container",
        },
    )
    assert custom.status_code == 200
    updated = custom.json()
    scenario_question = next(
        question for question in updated["questions"] if question["id"] == "scenarios"
    )
    assert scenario_question["options"][-1]["source"] == "teacher_custom"
    assert updated["draft"]["scenarios"] == ["Toy car stuck", "Snack container"]

    prompting = client.patch(
        f"/api/v2/lesson-chat/{state['conversationId']}/answers",
        json={
            "questionId": "prompting-strategy",
            "selectedOptionIds": ["wait-time", "fade-verbal"],
            "customAnswer": "Pause for five seconds",
        },
    )
    assert prompting.status_code == 200
    assert "Wait time before prompt" in prompting.json()["draft"]["promptingStart"]
    assert "Pause for five seconds" in prompting.json()["draft"]["promptingStart"]

    cleared = client.post(f"/api/v2/lesson-chat/{state['conversationId']}/clear")
    assert cleared.status_code == 200
    assert len(cleared.json()["messages"]) == 1
    assert cleared.json()["questions"]


def test_v2_product_lesson_package_pipeline_http_contract():
    client = TestClient(app)
    generated = client.post(
        "/api/v2/lesson-packages/generate",
        json={
            "id": "draft-product-package",
            "learnerId": "a102",
            "goalText": "Learner will ask for help using a short phrase.",
            "responseLevel": "Short phrase",
            "scenarios": ["Toy car stuck", "Closed box"],
            "selectedMaterials": ["Visual Cards", "Token Board", "Data Sheet"],
            "theme": "Vehicles",
            "duration": "10–12 min",
            "customNotes": "",
        },
    )
    assert generated.status_code == 201
    package = generated.json()
    assert package["safetyReview"]["status"] == "pass"
    assert package["safetyReview"]["riskLevel"] == "low"
    assert package["safetyReview"]["issues"] == []
    assert len(package["standardsChecks"]) == 13
    assert all(
        check["version"] == "instructional-quality-v1"
        for check in package["standardsChecks"]
    )
    assert [step["title"] for step in package["teachingFlow"]] == [
        "Warm-up and motivation",
        "Model asking for help",
        "Guided practice with prompts",
        "Independent opportunity",
        "Reinforcement and data note",
    ]
    assert [material["title"] for material in package["materials"]] == [
        "Visual Card",
        "Help Card",
        "Token Board",
        "Data Sheet",
        "Summary Template",
    ]
    token_board = next(
        material
        for material in package["materials"]
        if material["type"] == "token_board"
    )
    assert token_board["content"]["artwork"] == "Friendly vehicle artwork"
    assert token_board["content"]["teacherNote"] == (
        "Praise effort and reinforce each appropriate request."
    )

    package_id = package["id"]
    stored = client.get(f"/api/v2/lesson-packages/{package_id}")
    assert stored.status_code == 200
    assert stored.json() == package
    materials = client.get(f"/api/v2/lesson-packages/{package_id}/materials")
    assert materials.status_code == 200
    assert materials.json() == package["materials"]
    updated = client.patch(
        f"/api/v2/lesson-packages/{package_id}",
        json={
            "lessonBrief": "Teacher-edited package brief.",
            "documentContent": {"reinforcementPlan": "Praise and five tokens."},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["lessonBrief"] == "Teacher-edited package brief."
    assert updated.json()["documentContent"]["reinforcementPlan"] == (
        "Praise and five tokens."
    )
    assert updated.json()["materials"] == package["materials"]
    assert client.get("/api/v2/lesson-packages/not-found").status_code == 404


def test_v2_generated_material_editing_and_export_http_contract():
    client = TestClient(app)
    package = client.post(
        "/api/v2/lesson-packages/generate",
        json={
            "id": "draft-material-edit",
            "learnerId": "a102",
            "goalText": "Learner will ask for help using a short phrase.",
            "responseLevel": "Short phrase",
            "scenarios": ["Toy car stuck"],
            "selectedMaterials": ["Visual Cards", "Token Board", "Data Sheet"],
            "theme": "Vehicles",
            "duration": "10–12 min",
            "customNotes": "",
        },
    ).json()
    package_id = package["id"]
    visual, help_card, token = package["materials"][:3]

    updated = client.patch(
        f"/api/v2/generated-materials/{visual['id']}",
        json={
            "title": "My Visual Card",
            "content": {"instruction": "Please help."},
            "printLayout": {
                "pageSize": "A4",
                "orientation": "portrait",
                "color": "green",
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "teacher_review_needed"

    simplified = client.post(
        f"/api/v2/generated-materials/{visual['id']}/quick-edit",
        json={"action": "simplify_wording"},
    )
    assert simplified.json()["content"]["instruction"] == "Ask for help."
    artwork = client.post(
        f"/api/v2/generated-materials/{help_card['id']}/quick-edit",
        json={"action": "regenerate_artwork"},
    )
    assert artwork.json()["content"]["artwork"] == "Updated classroom artwork"
    reward = client.post(
        f"/api/v2/generated-materials/{token['id']}/quick-edit",
        json={"action": "adjust_reward"},
    )
    assert reward.json()["content"]["reward"] == "Choice activity"

    approved = client.post(f"/api/v2/generated-materials/{visual['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    stored_package = client.get(f"/api/v2/lesson-packages/{package_id}").json()
    stored_visual = next(
        material
        for material in stored_package["materials"]
        if material["id"] == visual["id"]
    )
    assert stored_visual["title"] == "My Visual Card"
    assert stored_visual["status"] == "approved"

    export = client.post(
        f"/api/v2/lesson-packages/{package_id}/export",
        json={"format": "zip", "materialIds": [], "reviewedConfirmation": True},
    )
    assert export.status_code == 200
    assert export.json()["status"] == "completed"
    assert export.json()["format"] == "zip"
    assert export.json()["downloadUrl"] is None
    assert export.json()["manifest"] == [
        "handoff-summary.pdf",
        "progress-data.csv",
        "handoff-data.json",
        "README.txt",
    ]


def test_v2_sessions_and_nonlinear_progress_http_contracts():
    client = TestClient(app)
    sessions = client.get("/api/v2/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()) == 4
    stats = client.get("/api/v2/sessions/stats")
    assert stats.status_code == 200
    assert [stat["status"] for stat in stats.json()] == [
        "planned",
        "in_progress",
        "completed",
        "draft",
    ]

    created = client.post(
        "/api/v2/sessions",
        json={
            "learnerId": "a102",
            "goal": "Generalize asking for help",
            "status": "planned",
        },
    )
    assert created.status_code == 201
    duplicated = client.post(f"/api/v2/sessions/{created.json()['id']}/duplicate")
    assert duplicated.status_code == 201
    assert duplicated.json()["status"] == "draft"
    summary = client.get("/api/v2/sessions/session-1/summary")
    assert summary.status_code == 200
    assert "not accuracy alone" in summary.json()["overview"]
    assert client.get("/api/v2/learners/a102/recent-lessons").status_code == 200

    progress = client.get("/api/v2/learners/a102/progress-summary")
    assert progress.status_code == 200
    assert progress.json()["message"] == "Plateau does not mean no progress."
    signals = client.get("/api/v2/learners/a102/progress-signals")
    assert [signal["label"] for signal in signals.json()] == [
        "Engagement",
        "Prompt Fading",
        "Generalization Attempts",
        "Regulation / Recovery",
        "Participation",
        "Independence",
    ]
    data = client.get("/api/v2/learners/a102/progress-data")
    assert [point["accuracyPercent"] for point in data.json()] == [
        52,
        55,
        53,
        56,
        54,
        58,
    ]
    assert [point["independencePercent"] for point in data.json()] == [
        28,
        31,
        33,
        35,
        38,
        42,
    ]
    assert data.json()[0]["promptLevel"] == "Level 3"
    assert data.json()[-1]["promptLevel"] == "Level 2"

    recorded = client.post(
        "/api/v2/session-data",
        json={
            "learnerId": "a102",
            "lessonPackageId": "package-demo",
            "goal": "Asking for Help",
            "opportunities": 10,
            "correct": 6,
            "independent": 5,
            "promptLevel": "Level 2",
            "signalsHighlighted": ["participation", "generalization"],
            "teacherNotes": "Two small independent wins in a new routine.",
        },
    )
    assert recorded.status_code == 201
    assert recorded.json()["accuracyPercent"] == 60
    assert recorded.json()["independencePercent"] == 50
    assert recorded.json()["sessionsPracticed"] == 18
    assert len(client.get("/api/v2/learners/a102/progress-data").json()) == 7


def test_durable_session_list_recovers_shortcuts_for_existing_lesson_packages():
    repos = V2Repositories()
    repos.is_durable = True
    package = V2LessonPackageService(repos).generate_product(
        LessonDesignDraftDto(
            id="historical-draft",
            learnerId="a102",
            goalText="Learner will complete a self-care routine.",
            responseLevel="Task sequence",
            scenarios=["Classroom routine"],
            selectedMaterials=["Visual Cards", "Data Sheet"],
            theme="Daily living",
            duration="10 min",
            customNotes="Teacher review required.",
        )
    )

    sessions = V2SessionService(repos).list()

    recovered = next(item for item in sessions if item.goal == package.goal)
    assert recovered.status == "planned"
    assert repos.sessions.get(recovered.id) is not None


def test_v2_material_library_browse_create_duplicate_and_attach():
    client = TestClient(app)
    materials = client.get("/api/v2/materials")
    assert materials.status_code == 200
    assert [material["title"] for material in materials.json()[:7]] == [
        "First-Then Card",
        "Emotion Card",
        "Token Board",
        "Data Sheet",
        "Choice Board",
        "Help Card",
        "Summary Template",
    ]
    assert "thumbnailLabel" in materials.json()[0]
    assert "createdAt" in materials.json()[0]

    created = client.post(
        "/api/v2/materials",
        json={
            "title": "Break Choice Card",
            "type": "Visual Cards",
            "thumbnailLabel": "Choose a break",
            "reusable": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["source"] == "template"

    duplicated = client.post(f"/api/v2/materials/{created.json()['id']}/duplicate")
    assert duplicated.status_code == 201
    assert duplicated.json()["title"] == "Break Choice Card Copy"

    chat = client.post("/api/v2/lesson-chat/start", json={"learnerId": "a102"}).json()
    attached = client.post(
        f"/api/v2/lesson-drafts/{chat['draft']['id']}/materials",
        json={"materialId": created.json()["id"]},
    )
    assert attached.status_code == 200
    assert attached.json()["selectedMaterials"] == ["Break Choice Card"]
    missing = client.post(
        "/api/v2/lesson-drafts/missing/materials",
        json={"materialId": created.json()["id"]},
    )
    assert missing.status_code == 404
