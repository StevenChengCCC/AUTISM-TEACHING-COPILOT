from base64 import b64encode

from app.core.config import Settings
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.schemas.v2_dto import ImageAssetDto, LessonDesignDraftDto
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
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


def fruit_identification_draft() -> LessonDesignDraftDto:
    return LessonDesignDraftDto(
        id="draft-fruit-identification-kit",
        learnerId="a102",
        goalText="Learner identifies pictures of apples and bananas when named.",
        observableResponse="Learner identifies pictures of apples and bananas when named.",
        responseLevel="Point or name",
        scenarios=["Table work"],
        selectedMaterials=[
            "Visual Cards",
            "Matching Practice",
            "Token Board",
            "Data Sheet",
            "Summary Template",
        ],
        theme="Fruit identification",
        duration="10 minutes",
        customNotes="Use clear object photographs or illustrations.",
    )


def test_object_identification_creates_varied_person_free_images_per_target(tmp_path):
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

    package = packages.generate_product(fruit_identification_draft())
    visual = next(item for item in package.materials if item.type == "visual_card")
    matching = next(item for item in package.materials if item.type == "matching_page")

    assert [item["label"] for item in visual.content["visualItems"]] == [
        "Apple",
        "Apple",
        "Apple",
        "Apple",
        "Banana",
        "Banana",
        "Banana",
        "Banana",
    ]
    assert [item["label"] for item in matching.content["visualItems"]] == [
        "Apple",
        "Banana",
    ]

    packages.queue_product_images(package.id)
    packages.prepare_product_images(package.id)
    completed = packages.get_product(package.id)
    visual = next(item for item in completed.materials if item.type == "visual_card")
    matching = next(item for item in completed.materials if item.type == "matching_page")

    # Each concept gets several varied exemplars rather than one repeated picture.
    object_calls = [
        call
        for call in provider.image_calls
        if call["materialType"] in {"visual card", "matching page"}
    ]
    assert len(object_calls) >= 8
    prompts = " ".join(call["prompt"] for call in object_calls)
    assert "one isolated Apple" in prompts
    assert "one isolated Banana" in prompts
    assert "Do not show a teacher" in prompts
    assert "surrounding scene" in prompts
    assert "classroom context" not in prompts
    assert len({item["imageAssetId"] for item in visual.content["visualItems"]}) == 8
    assert all(item["imageAssetId"] for item in matching.content["visualItems"])


def test_compound_identify_and_name_goal_uses_the_object_not_a_teaching_scene(
    tmp_path,
):
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
    draft = fruit_identification_draft().model_copy(
        update={
            "goalText": "Identify and name the apple.",
            "observableResponse": "Identify and name the apple.",
            "selectedMaterials": [
                "Visual Card",
                "Scenario Cards",
                "Reinforcement Board",
                "Data Sheet",
                "Lesson Summary",
            ],
        }
    )

    package = packages.generate_product(draft)
    assert {material.type for material in package.materials} == {
        "visual_card",
        "scenario_cards",
        "token_board",
        "data_sheet",
        "summary_template",
    }
    assert not any(check.status == "blocked" for check in package.standardsChecks)
    visual = next(item for item in package.materials if item.type == "visual_card")
    assert V2MaterialService(repos).approve_generated(visual.id).status == "approved"

    assert [item["label"] for item in visual.content["visualItems"]] == [
        "Apple",
        "Apple",
        "Apple",
        "Apple",
    ]
    packages.queue_product_images(package.id)
    packages.prepare_product_images(package.id)
    apple_call = next(
        call for call in provider.image_calls if call["materialType"] == "visual card"
    )
    assert "one isolated Apple" in apple_call["prompt"]
    assert "Do not show a teacher" in apple_call["prompt"]


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
    first_generation_call_count = len(provider.image_calls)
    assert first_generation_call_count >= 3

    second = packages.generate_product(lesson_draft())
    packages.queue_product_images(second.id)
    packages.prepare_product_images(second.id)
    second = packages.get_product(second.id)

    assert len(provider.image_calls) == first_generation_call_count
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
    assert len(generated_files) == first_generation_call_count
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
    first_generation_call_count = len(provider.image_calls)
    assert first_generation_call_count >= 3

    second = packages.generate_product(lesson_draft())
    packages.queue_product_images(second.id)
    packages.prepare_product_images(second.id)
    second = packages.get_product(second.id)

    assert len(provider.image_calls) == first_generation_call_count
    assert first.lessonBrief and second.lessonBrief
    for material in first.materials:
        if material.type in {"visual_card", "help_card", "token_board", "scenario_cards"}:
            assert material.content["imageSourceType"] in {"internal", "mock"}
            assert material.content["imageAssetId"]


def test_banana_request_does_not_reuse_stale_apple_visuals(tmp_path):
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
    draft = fruit_identification_draft().model_copy(
        update={
            "goalText": "Learner will identify a banana in pictures or real objects.",
            # Simulates stale provider copy from the previous turn.
            "observableResponse": "Learner will identify an apple.",
            "scenarios": ["Snack time"],
            "selectedMaterials": [
                "Visual Card",
                "Help Card",
                "Scenario Cards",
                "Data Sheet",
            ],
            "theme": "Banana identification",
        }
    )

    package = packages.generate_product(draft)
    visual = next(item for item in package.materials if item.type == "visual_card")
    help_card = next(item for item in package.materials if item.type == "help_card")

    assert [item["label"] for item in visual.content["visualItems"]] == [
        "Banana",
        "Banana",
        "Banana",
        "Banana",
    ]
    assert [item["label"] for item in help_card.content["visualItems"]] == [
        "Help, please."
    ]

    packages.queue_product_images(package.id)
    packages.prepare_product_images(package.id)
    prompts = " ".join(call["prompt"] for call in provider.image_calls)
    assert "Banana" in prompts
    assert "Apple" not in prompts


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
