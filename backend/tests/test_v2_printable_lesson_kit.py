from __future__ import annotations

from base64 import b64decode
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.integrations.mock_ai_provider import MockV2AIProvider
from app.integrations.private_object_storage import LocalPrivateObjectStorage
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    LessonPackageDto,
    LessonSectionEditPreviewRequest,
    PrintableLessonKitRequest,
    TeachingStepDto,
)
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_printable_lesson_kit_service import (
    V2PrintableLessonKitService,
)
from app.services.v2_repositories import V2Repositories


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV="test",
        V2_REPOSITORY_MODE="memory",
        OBJECT_STORAGE_PROVIDER="local",
        LOCAL_PRIVATE_STORAGE_DIR=str(tmp_path / "private"),
        LOCAL_UPLOAD_SIGNING_SECRET="test-print-kit-signing-secret",
        PUBLIC_API_BASE_URL="http://testserver",
        STORAGE_DIR=str(tmp_path / "public"),
        EXPORT_RETENTION_DAYS=7,
    )


def _seed_package(
    repos: V2Repositories, *, material_status: str = "approved"
) -> tuple[LessonPackageDto, list[GeneratedMaterialDto]]:
    materials = [
        GeneratedMaterialDto(
            id="counting-cards",
            packageId="counting-package",
            type="visual_card",
            title="Number Cards 1 to 5",
            status=material_status,
            content={
                "instruction": "Count from 1 to 5.",
                "examples": ["1", "2", "3", "4", "5"],
            },
            printLayout={"pageSize": "Letter", "orientation": "portrait"},
        ),
        GeneratedMaterialDto(
            id="counting-token-board",
            packageId="counting-package",
            type="token_board",
            title="Counting Token Board",
            status=material_status,
            content={
                "instruction": "Earn five tokens, then choose a break.",
                "tokens": 5,
                "reward": "Two-minute break",
            },
            printLayout={"pageSize": "Letter", "orientation": "portrait"},
        ),
        GeneratedMaterialDto(
            id="counting-data-sheet",
            packageId="counting-package",
            type="data_sheet",
            title="Counting Data Sheet",
            status=material_status,
            content={
                "columns": [
                    "Opportunity",
                    "Counted to",
                    "Prompt level",
                    "Notes",
                ]
            },
            printLayout={"pageSize": "Letter", "orientation": "portrait"},
        ),
    ]
    package = LessonPackageDto(
        id="counting-package",
        learnerId="a102",
        draftId="counting-draft",
        goal="The learner will count from 1 to 5 with teacher support.",
        duration="10 minutes",
        theme="Counting",
        lessonBrief="Practice counting with brief, structured turns.",
        teachingFlow=[
            TeachingStepDto(
                id="step-1",
                title="Warm-up",
                description="Preview the number cards.",
                duration="2 minutes",
                teacherAction="Point to each card and model the number.",
                learnerAction="Looks, points, or says the number.",
            )
        ],
        materials=materials,
        summaryTemplate="Record prompt level and participation.",
        documentContent={
            "title": "Counting 1 to 5",
            "goal": "The learner will count from 1 to 5 with teacher support.",
            "lessonBrief": "Practice counting with brief, structured turns.",
            "promptingPlan": "Use least-to-most prompting and fade support.",
            "reinforcementPlan": "Provide praise after each completed turn.",
            "dataCollectionPlan": "Record the highest number counted independently.",
        },
        status="approved",
        aiProvider="mock",
    )
    repos.lesson_packages.save(package)
    for material in materials:
        repos.generated_materials.save(material)
    return package, materials


def test_complete_printable_lesson_kit_is_one_real_multipage_pdf(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_package(repos)
    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)

    job = service.create(
        package.id,
        PrintableLessonKitRequest(
            materialIds=[item.id for item in materials],
            pageSize="Letter",
            reviewedConfirmation=True,
        ),
    )

    assert job.status == "completed"
    assert job.format == "pdf"
    assert job.fileName == "complete-lesson-kit.pdf"
    assert job.storageObjectKey
    assert package.learnerId not in job.storageObjectKey

    body = storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
    assert body.startswith(b"%PDF")
    reader = PdfReader(BytesIO(body))
    assert len(reader.pages) >= 4
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Counting 1 to 5" in text
    assert "Number Cards 1 to 5" in text
    assert "Counting Token Board" in text
    assert "Counting Data Sheet" in text
    for number in ("1", "2", "3", "4", "5"):
        assert number in text

    download = service.create_download(job.exportId)
    token = download.downloadUrl.rsplit("/", 1)[-1]
    downloaded, content_type, filename = storage.read_presigned_get(token)
    assert downloaded == body
    assert content_type == "application/pdf"
    assert filename == "complete-lesson-kit.pdf"


def test_complete_printable_lesson_kit_embeds_generated_image_url(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_package(repos)
    image_path = tmp_path / "public" / "generated-images" / "counting.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(
        b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
        )
    )
    visual = materials[0].model_copy(
        update={
            "content": {
                **materials[0].content,
                "imageUrl": "/storage/generated-images/counting.png",
                "imageAltText": "Five countable classroom objects.",
            }
        }
    )
    updated_materials = [visual, *materials[1:]]
    package = package.model_copy(update={"materials": updated_materials})
    repos.lesson_packages.save(package)
    repos.generated_materials.save(visual)

    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)
    job = service.create(
        package.id,
        PrintableLessonKitRequest(
            materialIds=[item.id for item in updated_materials],
            pageSize="Letter",
            reviewedConfirmation=True,
        ),
    )

    body = storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
    reader = PdfReader(BytesIO(body))
    embedded_images = 0
    for page in reader.pages:
        resources = page.get("/Resources")
        x_objects = resources.get("/XObject") if resources else None
        if not x_objects:
            continue
        for item in x_objects.values():
            resolved = item.get_object()
            if resolved.get("/Subtype") == "/Image":
                embedded_images += 1
    assert embedded_images >= 1


def test_visual_card_pdf_embeds_each_target_without_template_box(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_package(repos)
    generated_dir = tmp_path / "public" / "generated-images"
    generated_dir.mkdir(parents=True)
    tiny_png = b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )
    (generated_dir / "apple.png").write_bytes(tiny_png)
    (generated_dir / "banana.png").write_bytes(tiny_png)
    visual = materials[0].model_copy(
        update={
            "title": "Apple and Banana Visual Cards",
            "content": {
                **materials[0].content,
                "visualItems": [
                    {
                        "id": "apple",
                        "label": "Apple",
                        "imageUrl": "/storage/generated-images/apple.png",
                        "imageAltText": "One isolated apple.",
                        "generationStatus": "ready",
                    },
                    {
                        "id": "banana",
                        "label": "Banana",
                        "imageUrl": "/storage/generated-images/banana.png",
                        "imageAltText": "One isolated banana.",
                        "generationStatus": "ready",
                    },
                ],
            },
        }
    )
    updated_materials = [visual, *materials[1:]]
    repos.generated_materials.save(visual)
    repos.lesson_packages.save(package.model_copy(update={"materials": updated_materials}))
    service = V2PrintableLessonKitService(
        repos, LocalPrivateObjectStorage(config), config
    )

    job = service.create(
        package.id,
        PrintableLessonKitRequest(
            materialIds=[item.id for item in updated_materials],
            pageSize="Letter",
            reviewedConfirmation=True,
        ),
    )

    body = LocalPrivateObjectStorage(config).read_bytes(
        job.storageObjectKey, config.MAX_EXPORT_BYTES
    )
    reader = PdfReader(BytesIO(body))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Apple" in text
    assert "Banana" in text
    commands = V2PrintableLessonKitService._visual_sheet_style().getCommands()
    assert all(command[0] not in {"BOX", "GRID"} for command in commands)


def test_selected_material_design_controls_print_palette():
    blue = V2PrintableLessonKitService._design_palette(
        {"selectedDesignVariant": "calm-blue"}
    )
    green = V2PrintableLessonKitService._design_palette(
        {"selectedDesignVariant": "playful-green"}
    )
    gold = V2PrintableLessonKitService._design_palette(
        {"selectedDesignVariant": "warm-gold"}
    )

    assert blue["accent"].hexval() == "0x2563eb"
    assert green["accent"].hexval() == "0x16a34a"
    assert gold["accent"].hexval() == "0xd97706"
    assert len({blue["soft"].hexval(), green["soft"].hexval(), gold["soft"].hexval()}) == 3


def test_printable_lesson_kit_rejects_incomplete_planned_visuals(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_package(repos)
    visual = materials[0].model_copy(
        update={
            "content": {
                **materials[0].content,
                "visualItems": [
                    {
                        "id": "count-1",
                        "label": "1",
                        "quantity": 1,
                        "generationStatus": "ready",
                        "imageUrl": "/storage/generated-images/counting.png",
                    },
                    {
                        "id": "count-2",
                        "label": "2",
                        "quantity": 2,
                        "generationStatus": "pending",
                        "imageUrl": None,
                    },
                ],
            }
        }
    )
    repos.generated_materials.save(visual)
    repos.lesson_packages.save(
        package.model_copy(update={"materials": [visual, *materials[1:]]})
    )
    service = V2PrintableLessonKitService(
        repos, LocalPrivateObjectStorage(config), config
    )

    with pytest.raises(
        ConflictError, match="Every planned classroom visual must be ready"
    ):
        service.create(
            package.id,
            PrintableLessonKitRequest(
                materialIds=[item.id for item in [visual, *materials[1:]]],
                pageSize="Letter",
                reviewedConfirmation=True,
            ),
        )


def test_printable_lesson_kit_requires_teacher_approved_materials(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, materials = _seed_package(
        repos, material_status="teacher_review_needed"
    )
    service = V2PrintableLessonKitService(
        repos, LocalPrivateObjectStorage(config), config
    )

    with pytest.raises(ConflictError, match="Approve all selected materials"):
        service.create(
            package.id,
            PrintableLessonKitRequest(
                materialIds=[item.id for item in materials],
                reviewedConfirmation=True,
            ),
        )


def test_scoped_ai_edit_returns_preview_without_saving_other_sections(tmp_path):
    config = _settings(tmp_path)
    repos = V2Repositories()
    package, _ = _seed_package(repos)
    before = repos.lesson_packages.get(package.id)
    service = V2LessonPackageService(
        repos,
        ai=MockV2AIProvider(config),
        config=config,
    )

    preview = service.preview_section_edit(
        package.id,
        LessonSectionEditPreviewRequest(
            sectionId="lessonBrief",
            sectionLabel="Lesson brief",
            currentText=package.lessonBrief,
            instruction="Shorten this selected section for printing.",
            expectedVersion=package.version,
        ),
    )

    assert preview.sectionId == "lessonBrief"
    assert preview.beforeText == package.lessonBrief
    assert preview.revisedText
    assert preview.revisedText != preview.beforeText
    assert preview.providerUsed == "mock"
    assert repos.lesson_packages.get(package.id) == before
