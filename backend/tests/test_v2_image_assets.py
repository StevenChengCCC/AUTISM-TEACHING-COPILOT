from fastapi.testclient import TestClient

from app.main import app
from app.schemas.v2_dto import (
    ApproveImageAssetRequest,
    ImageSearchRequest,
    LessonDesignDraftDto,
)
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories


def test_image_asset_seed_library_is_complete_and_safe():
    service = V2ImageAssetService(V2Repositories())

    assets = service.get_seed_assets()

    assert len(assets) == 10
    assert {asset.concept for asset in assets} == {
        "toy car",
        "toy car stuck",
        "closed box",
        "backpack zipper",
        "snack container",
        "puzzle piece missing",
        "help card icon",
        "token board star",
        "visual prompt card",
        "classroom table",
    }
    assert all(asset.approved for asset in assets)
    assert all(asset.safetyStatus == "ready" for asset in assets)
    assert all(asset.licenseInfo == "Internal demo asset" for asset in assets)
    assert all(asset.sourceType in {"internal", "mock"} for asset in assets)


def test_image_asset_dto_serializes_with_frontend_friendly_fields():
    asset = V2ImageAssetService(V2Repositories()).get_seed_assets()[0]

    payload = asset.model_dump(mode="json", by_alias=True)

    assert "sourceType" in payload
    assert "imageUrl" in payload
    assert "licenseInfo" in payload
    assert "safetyStatus" in payload
    assert "source_type" not in payload


def test_internal_candidate_matching_is_deterministic_and_limited():
    service = V2ImageAssetService(V2Repositories())

    candidates = service.find_internal_candidates(
        "toy car stuck", "visual_card", max_results=2
    )

    assert len(candidates) == 2
    assert candidates[0].concept == "toy car stuck"
    assert all(candidate.approved for candidate in candidates)
    assert all(candidate.sourceType == "internal" for candidate in candidates)


def test_asset_filters_support_partial_concepts_and_approval():
    service = V2ImageAssetService(V2Repositories())

    candidates = service.list_assets(concept="zipper", approved=True)

    assert [asset.concept for asset in candidates] == ["backpack zipper"]


def test_image_search_request_defaults_do_not_enable_generation():
    request = ImageSearchRequest(concept="closed box", materialType="visual_card")

    assert request.maxResults == 6
    assert request.allowExternalSearch is True
    assert request.allowGeneration is False


def test_candidate_response_is_internal_only_and_does_not_offer_generation():
    service = V2ImageAssetService(V2Repositories(), external_providers=[])

    response = service.get_image_candidates(
        ImageSearchRequest(
            concept="toy car stuck",
            materialType="visual_card",
            allowExternalSearch=True,
            allowGeneration=True,
        )
    )

    assert response.sourceOrder == ["internal"]
    assert response.generationAvailable is False
    assert response.fallbackUsed is False
    assert response.candidates
    assert response.candidates[0].concept == "toy car stuck"


def test_candidate_response_explains_internal_miss():
    response = V2ImageAssetService(
        V2Repositories(), external_providers=[]
    ).get_image_candidates(
        ImageSearchRequest(concept="spaceship helmet", materialType="visual_card")
    )

    assert response.candidates == []
    assert response.message == "No image candidates found. Teacher may try a different concept or explicitly generate an image."


def test_approval_attaches_asset_metadata_to_existing_generated_material():
    repos = V2Repositories()
    package = V2LessonPackageService(repos).generate_product(
        LessonDesignDraftDto(
            id="draft-image-test",
            learnerId="a102",
            goalText="Learner will ask for help using a short phrase.",
            responseLevel="Short phrase",
            scenarios=["Toy car stuck"],
            selectedMaterials=["Visual Cards", "Help Card"],
            theme="Vehicles",
            duration="10–12 min",
            customNotes="Use visual support.",
        )
    )
    material = package.materials[0]

    approved = V2ImageAssetService(repos).approve_asset(
        "asset-toy-car-stuck",
        ApproveImageAssetRequest(
            assetId="asset-toy-car-stuck", materialId=material.id
        ),
    )

    stored = repos.generated_materials.get(material.id)
    assert approved.approved is True
    assert approved.safetyStatus == "ready"
    assert stored is not None
    assert stored.content["imageAssetId"] == approved.id
    assert stored.content["imageUrl"] == approved.imageUrl
    assert stored.content["imageAltText"] == approved.altText
    assert stored.content["imageSourceType"] == approved.sourceType
    assert stored.content["imageLicenseInfo"] == approved.licenseInfo


def test_approval_succeeds_when_material_does_not_exist():
    service = V2ImageAssetService(V2Repositories())

    approved = service.approve_asset(
        "asset-closed-box",
        ApproveImageAssetRequest(
            assetId="asset-closed-box", materialId="missing-material"
        ),
    )

    assert approved.approved is True
    assert approved.safetyStatus == "ready"


def test_image_asset_http_routes_return_camel_case_contracts():
    client = TestClient(app)

    candidates = client.post(
        "/api/v2/image-assets/candidates",
        json={
            "concept": "toy car stuck",
            "materialType": "visual_card",
            "learnerId": "a102",
            "maxResults": 6,
            "allowExternalSearch": False,
            "allowGeneration": False,
        },
    )
    assets = client.get("/api/v2/image-assets?concept=toy%20car&approved=true")

    assert candidates.status_code == 200
    assert candidates.json()["sourceOrder"] == ["internal"]
    assert candidates.json()["generationAvailable"] is False
    assert candidates.json()["candidates"][0]["sourceType"] == "internal"
    assert assets.status_code == 200
    assert assets.json()
    assert "safetyStatus" in assets.json()[0]


def test_generate_candidate_route_remains_available_in_mock_mode():
    client = TestClient(app)

    response = client.post(
        "/api/v2/image-assets/generate-candidate",
        json={
            "learnerId": "a102",
            "materialType": "visual_card",
            "concept": "toy car stuck",
            "prompt": "A generic toy car visual with no identifying details.",
            "style": "clean printable educational illustration",
            "size": "1024x1024",
        },
    )

    assert response.status_code == 200
    assert response.json()["sourceType"] in {"internal", "mock"}
    assert response.json()["approved"] in {True, False}
    assert "safetyStatus" in response.json()
