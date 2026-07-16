from fastapi.testclient import TestClient

from app.main import app


def test_round7_demo_journey_from_learner_to_private_handoff():
    """One synthetic HTTP journey complements the focused persistence/upload tests."""

    client = TestClient(app)
    me = client.get("/api/v2/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticationMode"] == "demo"

    learners = client.get("/api/v2/learners")
    assert learners.status_code == 200
    assert any(item["id"] == "a102" for item in learners.json())
    extraction = client.get("/api/v2/learners/a102/profile-extraction")
    assert extraction.status_code == 200
    assert extraction.json()["status"] == "complete"
    confirmed_profile = client.post(
        "/api/v2/learners/a102/profile/confirm",
        json={"expectedVersion": extraction.json()["learner"]["version"]},
    )
    assert confirmed_profile.status_code == 200
    assert confirmed_profile.json()["profileReviewStatus"] == "confirmed"

    chat = client.post("/api/v2/lesson-chat/start", json={"learnerId": "a102"})
    assert chat.status_code == 201
    state = chat.json()
    planned = client.post(
        "/api/v2/lesson-chat/message",
        json={
            "conversationId": state["conversationId"],
            "learnerId": "a102",
            "message": "I want to teach asking for help.",
            "currentDraft": state["draft"],
        },
    )
    assert planned.status_code == 200
    assert planned.json()["questions"]

    generated = client.post(
        "/api/v2/lesson-packages/generate", json=planned.json()["draft"]
    )
    assert generated.status_code == 201
    package = generated.json()
    approved_package = client.post(
        f"/api/v2/lesson-packages/{package['id']}/approve",
        json={"expectedVersion": package["version"], "reason": "Synthetic review"},
    )
    assert approved_package.status_code == 200
    assert approved_package.json()["status"] == "approved"

    material = package["materials"][0]
    approved_material = client.post(
        f"/api/v2/generated-materials/{material['id']}/approve"
    )
    assert approved_material.status_code == 200
    assert approved_material.json()["status"] == "approved"

    session = client.post(
        "/api/v2/sessions",
        json={"learnerId": "a102", "goal": "Asking for Help", "status": "planned"},
    )
    assert session.status_code == 201
    observation = client.post(
        "/api/v2/session-data",
        json={
            "learnerId": "a102",
            "lessonPackageId": package["id"],
            "goal": "Asking for Help",
            "opportunities": 5,
            "correct": 3,
            "independent": 2,
            "promptLevel": "Level 2",
            "signalsHighlighted": ["participation", "prompt_fading"],
            "teacherNotes": "Synthetic small win with less prompting.",
        },
    )
    assert observation.status_code == 201
    assert observation.json()["message"] == "Plateau does not mean no progress."

    handoff = client.post(
        "/api/v2/learners/a102/handoff-exports",
        json={
            "sections": {
                "learnerOverview": True,
                "teachingStrategies": True,
                "activeGoals": True,
                "progress": True,
                "recentSessions": True,
                "lessonPackages": True,
                "approvedMaterials": True,
                "transitionNotes": True,
            },
            "dateRange": {},
            "sessionIds": [session.json()["id"]],
            "packageIds": [package["id"]],
            "materialIds": [material["id"]],
            "transitionNotes": "Synthetic authorized handoff note.",
            "includePrintableMaterials": True,
            "pageSize": "Letter",
            "orientation": "portrait",
            "reviewedConfirmation": True,
        },
    )
    assert handoff.status_code == 201
    assert handoff.json()["status"] == "completed"
    download = client.post(
        f"/api/v2/handoff-exports/{handoff.json()['exportId']}/download"
    )
    assert download.status_code == 200
    assert "/api/v2/exports/local/" in download.json()["downloadUrl"]

    # A fresh browser/API client can resolve the durable resource IDs. SQL/S3
    # restart survival is exercised by the focused Round 2 and Round 6 suites.
    refreshed = TestClient(app)
    assert refreshed.get(f"/api/v2/lesson-packages/{package['id']}").status_code == 200
    assert any(
        item["id"] == package["id"]
        for item in refreshed.get(
            "/api/v2/lesson-packages?learnerId=a102"
        ).json()
    )
    assert any(
        item["exportId"] == handoff.json()["exportId"]
        for item in refreshed.get("/api/v2/handoff-exports?learnerId=a102").json()
    )
