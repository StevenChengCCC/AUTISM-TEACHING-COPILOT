from __future__ import annotations

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
