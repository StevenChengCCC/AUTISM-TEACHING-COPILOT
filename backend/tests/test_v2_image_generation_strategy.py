from base64 import b64encode

from app.core.config import Settings
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.schemas.v2_dto import ImageAssetDto, LessonDesignDraftDto
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories


class CountingImageProvider(MockV2AIProvider):
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.image_calls = []

    def generate_material_image(
        self, learner, material_type, prompt, style=None, size=None
    ):
        self.image_calls.append(
            {
                "learnerId": learner.id,
                "materialType": material_type,
                "prompt": prompt,
                "style": style,
                "size": size,
            }
        )
        if self.fail:
            raise RuntimeError("simulated provider failure")
        return {
            "imageId": f"provider-{material_type}",
            "status": "ready",
            "imageUrl": None,
            "imageBase64": b64encode(b"demo-image-bytes").decode(),
            "promptUsed": prompt,
            "fallbackUsed": False,
        }


class MissingImageFieldsProvider(CountingImageProvider):
    """Simulate valid provider material copy that omitted image metadata."""

    def generate_lesson_package(self, draft, learner_context=None):
        generated = super().generate_lesson_package(draft, learner_context)
        for material in generated["materials"]:
            material.pop("imageConcept", None)
            material.pop("imagePrompt", None)
            material.pop("imageAltText", None)
        return generated


class OneResultExternalProvider:
    provider_name = "test-external"

    def __init__(self):
        self.calls = []

    def search(self, concept, material_type, max_results):
        self.calls.append((concept, material_type, max_results))
        return [
            ImageAssetDto(
                id=f"external-{material_type}",
                sourceType="pexels",
                title="External classroom visual",
                concept=concept,
                imageUrl="https://images.example/classroom.jpg",
                thumbnailUrl="https://images.example/classroom-thumb.jpg",
                altText=f"External candidate for {concept}.",
                tags=[concept, material_type],
                licenseInfo="Pexels License",
                attribution="Photo by Example on Pexels",
                providerAssetId=f"external-{material_type}",
                approved=False,
                safetyStatus="needs_review",
                createdAt="2025-05-12T10:21:00Z",
            )
        ]


def lesson_draft() -> LessonDesignDraftDto:
    return LessonDesignDraftDto(
        id="draft-image-strategy",
        learnerId="a102",
        goalText="Learner will ask for help using a short phrase.",
        responseLevel="Short phrase",
        scenarios=["Toy car stuck", "Closed box"],
        selectedMaterials=[
            "Visual Cards",
            "Help Card",
            "Token Board",
            "Data Sheet",
            "Summary Template",
        ],
        theme="Vehicles",
        duration="10–12 min",
        customNotes="Use a visual prompt first.",
    )


def counting_draft() -> LessonDesignDraftDto:
    return LessonDesignDraftDto(
        id="draft-counting-kit",
        learnerId="a102",
        goalText="Learner will count from 1 to 5.",
        observableResponse="Learner will count objects from 1 to 5.",
        responseLevel="Point and count",
        scenarios=["Table work"],
        selectedMaterials=[
            "Quantity Cards",
            "Matching Practice",
            "Reinforcement Board",
            "Data Sheet",
            "Lesson Summary",
        ],
        theme="Vehicles",
        duration="8 minutes",
        customNotes="Use the learner's interests.",
    )


def test_counting_cards_use_repeated_personalized_object_not_generic_dots(tmp_path):
    repos = V2Repositories()
    provider = CountingImageProvider()
    config = Settings(
        _env_file=None,
        IMAGE_ASSET_STRATEGY="generate_first",
        STORAGE_DIR=str(tmp_path),
    )
    images = V2ImageAssetService(
        repos, external_providers=[], ai=provider, config=config
    )
    packages = V2LessonPackageService(repos, ai=provider, images=images)

    package = packages.generate_product(counting_draft())
    visual = next(item for item in package.materials if item.type == "quantity_cards")
    planned = visual.content["visualItems"]
    assert [item["quantity"] for item in planned] == [1, 2, 3, 4, 5]
    assert all(item["assetRole"] == "countable_object" for item in planned)

    packages.queue_product_images(package.id)
    packages.prepare_product_images(package.id)
    visual = next(
        item
        for item in packages.get_product(package.id).materials
        if item.type == "quantity_cards"
    )
    completed = visual.content["visualItems"]
    visual_calls = [
        call
        for call in provider.image_calls
        if call["materialType"] == "quantity cards"
    ]
    assert len(visual_calls) == 1
    assert len({item["imageAssetId"] for item in completed}) == 1
    assert all(item["imageUrl"] for item in completed)


def test_generate_first_adds_complete_reviewable_visual_set_and_reuses_cache(tmp_path):
    repos = V2Repositories()
    provider = CountingImageProvider()
    config = Settings(
        _env_file=None,
        IMAGE_ASSET_STRATEGY="generate_first",
        STORAGE_DIR=str(tmp_path),
    )
    images = V2ImageAssetService(
        repos, external_providers=[], ai=provider, config=config
    )
    packages = V2LessonPackageService(repos, ai=provider, images=images)

    first = packages.generate_product(lesson_draft())
    assert provider.image_calls == []
    first = packages.queue_product_images(first.id)
    assert all(
        material.content.get("imageGenerationStatus") == "pending"
        for material in first.materials
        if material.type in {"visual_card", "help_card", "token_board"}
    )
    packages.prepare_product_images(first.id)
    first = packages.get_product(first.id)

    second = packages.generate_product(lesson_draft())
    packages.queue_product_images(second.id)
    packages.prepare_product_images(second.id)
    second = packages.get_product(second.id)

    assert len(provider.image_calls) == 3
    visual_types = {"visual_card", "help_card", "token_board", "scenario_cards"}
    for package in (first, second):
        for material in package.materials:
            if material.type in visual_types:
                assert material.content["imageAssetId"]
                assert material.content["imageUrl"].startswith(
                    "/storage/generated-images/"
                )
                assert material.content["imageBase64"] is None
                assert material.content["imageSourceType"] == "generated"
                assert material.content["imageSafetyStatus"] == "needs_review"
                assert "teacher review required" in material.content[
                    "imageLicenseInfo"
                ]
            else:
                assert "imageAssetId" not in material.content
    generated_files = list((tmp_path / "generated-images").glob("*.png"))
    assert len(generated_files) == 3
    prompts = " ".join(call["prompt"] for call in provider.image_calls)
    assert "Learner A-102" not in prompts
    assert "visual prompts and concise instructions" not in prompts


def test_failed_generation_still_builds_package_and_caches_fallback():
    repos = V2Repositories()
    provider = CountingImageProvider(fail=True)
    config = Settings(_env_file=None, IMAGE_ASSET_STRATEGY="generate_first")
    images = V2ImageAssetService(
        repos, external_providers=[], ai=provider, config=config
    )
    packages = V2LessonPackageService(repos, ai=provider, images=images)

    first = packages.generate_product(lesson_draft())
    packages.queue_product_images(first.id)
    packages.prepare_product_images(first.id)
    first = packages.get_product(first.id)

    second = packages.generate_product(lesson_draft())
    packages.queue_product_images(second.id)
    packages.prepare_product_images(second.id)
    second = packages.get_product(second.id)

    assert len(provider.image_calls) == 3
    assert first.lessonBrief and second.lessonBrief
    for material in first.materials:
        if material.type in {"visual_card", "help_card", "token_board", "scenario_cards"}:
            assert material.content["imageSourceType"] in {"internal", "mock"}
            assert material.content["imageAssetId"]


def test_visual_materials_do_not_silently_skip_images_when_provider_omits_concept(
    tmp_path,
):
    repos = V2Repositories()
    provider = MissingImageFieldsProvider()
    config = Settings(
        _env_file=None,
        IMAGE_ASSET_STRATEGY="generate_first",
        STORAGE_DIR=str(tmp_path),
    )
    images = V2ImageAssetService(
        repos, external_providers=[], ai=provider, config=config
    )
    packages = V2LessonPackageService(repos, ai=provider, images=images)

    package = packages.generate_product(lesson_draft())
    visual_materials = [
        material
        for material in package.materials
        if material.type in packages.image_material_types
    ]

    assert visual_materials
    assert all(material.content.get("imageConcept") for material in visual_materials)
    assert all(material.content.get("imagePrompt") for material in visual_materials)

    packages.queue_product_images(package.id)
    packages.prepare_product_images(package.id)
    completed = packages.get_product(package.id)

    assert provider.image_calls
    assert all(
        material.content.get("imageUrl")
        for material in completed.materials
        if material.type in packages.image_material_types
    )


def test_reuse_search_generate_uses_external_candidate_before_generation():
    repos = V2Repositories()
    provider = CountingImageProvider()
    external = OneResultExternalProvider()
    config = Settings(
        _env_file=None, IMAGE_ASSET_STRATEGY="reuse_search_generate"
    )
    images = V2ImageAssetService(
        repos,
        external_providers=[external],
        ai=provider,
        config=config,
    )

    asset = images.prepare_generated_image_for_material(
        learner_id="a102",
        material_id="missing-material",
        material_type="visual_card",
        concept="new classroom concept",
        prompt="A generic classroom visual with no identifying information.",
    )

    assert provider.image_calls == []
    assert external.calls == [("new classroom concept", "visual card", 1)]
    assert asset.sourceType == "pexels"
    assert asset.approved is False
    assert asset.safetyStatus == "needs_review"


def test_mock_mode_needs_no_key_and_never_images_data_or_summary_materials():
    repos = V2Repositories()
    config = Settings(
        _env_file=None,
        AI_PROVIDER="mock",
        OPENAI_API_KEY=None,
        IMAGE_ASSET_STRATEGY="generate_first",
    )
    images = V2ImageAssetService(repos, external_providers=[], config=config)
    package = V2LessonPackageService(repos, images=images).generate_product(
        lesson_draft()
    )

    assert package.lessonBrief
    assert all(
        "imageAssetId" not in material.content
        for material in package.materials
        if material.type in {"data_sheet", "summary_template"}
    )
