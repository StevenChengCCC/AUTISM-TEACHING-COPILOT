from app.core.config import Settings
from app.integrations.pexels_image_provider import PexelsImageProvider
from app.schemas.v2_dto import ImageAssetDto, ImageSearchRequest
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_repositories import V2Repositories


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


class FakeExternalProvider:
    provider_name = "fake-search"

    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, concept, material_type, max_results):
        self.calls.append((concept, material_type, max_results))
        return self.results[:max_results]


def external_asset(asset_id="external-1", image_url="https://images.example/1.jpg"):
    return ImageAssetDto(
        id=asset_id,
        sourceType="pexels",
        title="Toy car photo",
        concept="toy car",
        imageUrl=image_url,
        thumbnailUrl="https://images.example/1-thumb.jpg",
        altText="A toy car on a plain surface.",
        tags=["toy car", "visual card"],
        licenseInfo="Pexels License",
        attribution="Photo by Example Photographer on Pexels",
        providerAssetId="123",
        approved=False,
        safetyStatus="needs_review",
        createdAt="2025-05-12T10:21:00Z",
    )


def test_pexels_returns_empty_without_key_and_does_not_make_request():
    session = FakeSession({"photos": []})
    provider = PexelsImageProvider(
        Settings(_env_file=None, PEXELS_API_KEY=None), session=session
    )

    assert provider.search("toy car", "visual_card", 6) == []
    assert session.calls == []


def test_pexels_maps_public_photo_metadata_without_exposing_key():
    session = FakeSession(
        {
            "photos": [
                {
                    "id": 42,
                    "photographer": "Example Photographer",
                    "alt": "A small blue toy car",
                    "src": {
                        "large2x": "https://images.pexels.com/car-large.jpg",
                        "medium": "https://images.pexels.com/car-medium.jpg",
                    },
                }
            ]
        }
    )
    provider = PexelsImageProvider(
        Settings(_env_file=None, PEXELS_API_KEY="secret-test-value"),
        session=session,
    )

    assets = provider.search("toy car", "visual_card", 2)

    assert len(assets) == 1
    assert assets[0].sourceType == "pexels"
    assert assets[0].providerAssetId == "42"
    assert assets[0].approved is False
    assert assets[0].safetyStatus == "needs_review"
    assert assets[0].licenseInfo == "Pexels License"
    assert session.calls[0][1]["params"]["query"] == "toy car"
    assert "secret-test-value" not in assets[0].model_dump_json()


def test_internal_results_prevent_unnecessary_external_search():
    provider = FakeExternalProvider([external_asset()])
    service = V2ImageAssetService(
        V2Repositories(), external_providers=[provider]
    )

    response = service.get_image_candidates(
        ImageSearchRequest(
            concept="toy car stuck", materialType="visual_card", maxResults=1
        )
    )

    assert provider.calls == []
    assert response.sourceOrder == ["internal"]
    assert response.message == "Found approved internal assets."


def test_external_search_uses_only_generic_concept_and_deduplicates_results():
    duplicate = external_asset(asset_id="external-duplicate")
    provider = FakeExternalProvider([external_asset(), duplicate])
    repos = V2Repositories()
    service = V2ImageAssetService(repos, external_providers=[provider])

    response = service.get_image_candidates(
        ImageSearchRequest(
            concept="spaceship helmet",
            materialType="visual_card",
            learnerId="a102",
            maxResults=6,
            allowExternalSearch=True,
        )
    )

    assert provider.calls == [("spaceship helmet", "visual_card", 6)]
    assert response.sourceOrder == ["internal", "fake-search"]
    assert len(response.candidates) == 1
    assert response.message == "Found internal and external image candidates for teacher review."
    stored = repos.image_assets.get("external-1")
    assert stored is not None
    assert stored.approved is False


def test_allow_external_search_false_never_calls_provider():
    provider = FakeExternalProvider([external_asset()])
    response = V2ImageAssetService(
        V2Repositories(), external_providers=[provider]
    ).get_image_candidates(
        ImageSearchRequest(
            concept="spaceship helmet",
            materialType="visual_card",
            allowExternalSearch=False,
        )
    )

    assert provider.calls == []
    assert response.sourceOrder == ["internal"]
    assert response.candidates == []
