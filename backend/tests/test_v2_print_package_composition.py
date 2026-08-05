from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.platypus import Table

from app.core.exceptions import ConflictError, ValidationError
from app.integrations.private_object_storage import LocalPrivateObjectStorage
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    LessonPackageDecisionRequest,
    PrintableLessonKitRequest,
)
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_repositories import V2Repositories
from test_v2_printable_lesson_kit import _seed_package, _settings
from test_v2_semantic_revision import n482_runtime


FIXTURES = Path(__file__).parent / "fixtures"


def _pdf_text(reader: PdfReader) -> str:
    return " ".join(
        "\n".join(page.extract_text() or "" for page in reader.pages).split()
    )


def _approve_n482():
    repos, package = n482_runtime()
    material_service = V2MaterialService(repos)
    for material in package.materials:
        material_service.review_generated(material.id)
        material_service.approve_generated(material.id)
    package_service = V2LessonPackageService(repos)
    current = package_service.get_product(package.id)
    approved = package_service.approve_product(
        current.id,
        LessonPackageDecisionRequest(
            expectedVersion=current.version,
            reason="N-482 print composition acceptance test",
        ),
    )
    return repos, approved


def test_n482_print_manifest_matches_golden_and_canonical_order():
    repos, package = _approve_n482()
    service = V2PrintableLessonKitService(repos)
    manifest = service.build_manifest(package, package.materials, page_size="Letter")
    actual = manifest.model_dump(mode="json", by_alias=True)
    actual.pop("generatedAt")
    actual.pop("pageCount")
    actual["sourceApprovalReadinessEvidence"].pop("evaluatedAt")
    expected = json.loads(
        (FIXTURES / "n482_print_manifest_golden.json").read_text(encoding="utf-8")
    )

    assert actual == expected
    material_ids = [
        material_id
        for section in manifest.sections
        for material_id in section.materialIds
    ]
    expected_types = [
        "blue_line_activity",
        "break_card",
        "first_then_board",
        "token_board",
        "visual_timer",
        "teacher_cue_card",
        "scenario_cards",
        "data_sheet",
        "summary_template",
    ]
    type_by_id = {item.id: item.type for item in package.materials}
    assert [type_by_id[item_id] for item_id in material_ids] == expected_types


def test_n482_complete_approved_package_persists_one_valid_mixed_layout_pdf(tmp_path):
    repos, package = _approve_n482()
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)

    job = service.create(
        package.id,
        PrintableLessonKitRequest(
            materialIds=[item.id for item in package.materials],
            pageSize="Letter",
            reviewedConfirmation=True,
        ),
    )

    body = storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
    reader = PdfReader(BytesIO(body))
    text = _pdf_text(reader)
    assert body.startswith(b"%PDF") and len(body) > 0
    assert job.fileName == "learner-N-482-break-request-kit-letter-standard.pdf"
    # Renderer v5 keeps the Standard Classroom Run Sheet to two pages.
    assert job.pageCount == len(reader.pages) == 17
    assert job.printPackageManifest.pageCount == len(reader.pages)
    assert job.artifactSha256 and len(job.artifactSha256) == 64
    assert any(float(page.mediabox.width) < float(page.mediabox.height) for page in reader.pages)
    assert any(float(page.mediabox.width) > float(page.mediabox.height) for page in reader.pages)
    for phrase in (
        "Complete the Blue Line",
        "Station cards",
        "Break, please",
        "Complete 3 table-work items",
        "2-minute transit-map break",
        "Reinforcement Board",
        "2:00 visual-only countdown",
        "Scenario Cards 1",
        "Scenario Cards 2",
        "Scenario Cards 3",
        "Opportunity Context Response Outcome",
        "Lesson Summary",
        "Classroom Run Sheet",
        "Before class",
        "Two-minute closeout",
        "Teacher judgment overrides this guide",
        "Page 17",
    ):
        assert phrase.casefold() in text.casefold()


def test_package_content_plan_material_cannot_be_silently_omitted():
    repos, package = n482_runtime()
    service = V2PrintableLessonKitService(repos)
    requested = [item.id for item in package.materials[:-1]]

    with pytest.raises(ValidationError) as error:
        service._resolve_current_package_materials(package, requested)

    assert error.value.payload["omittedMaterialIds"]
    assert error.value.payload["unknownMaterialIds"] == []


def test_ready_visual_with_missing_asset_fails_closed(tmp_path):
    repos = V2Repositories()
    package, materials = _seed_package(repos)
    broken = materials[0].model_copy(
        update={
            "content": {
                **materials[0].content,
                "visualItems": [
                    {
                        "id": "missing-ready-asset",
                        "label": "1",
                        "required": True,
                        "generationStatus": "ready",
                        "imageUrl": "/storage/generated-images/missing.png",
                    }
                ],
            }
        }
    )
    repos.generated_materials.save(broken)
    repos.lesson_packages.save(
        package.model_copy(update={"materials": [broken, *materials[1:]]})
    )
    service = V2PrintableLessonKitService(
        repos,
        LocalPrivateObjectStorage(_settings(tmp_path)),
        _settings(tmp_path),
    )

    with pytest.raises(
        ConflictError, match="storage_download_preparation_failure"
    ):
        service.create(
            package.id,
            PrintableLessonKitRequest(
                materialIds=[broken.id, *[item.id for item in materials[1:]]],
                pageSize="Letter",
                reviewedConfirmation=True,
            ),
        )


def test_long_data_sheet_repeats_header_on_continuation_pages():
    repos, package = n482_runtime()
    columns = next(
        item.materialSpec.content.exact_columns
        for item in package.materials
        if item.type == "data_sheet"
    )
    long_sheet = GeneratedMaterialDto(
        id="long-data-sheet",
        packageId=package.id,
        type="data_sheet",
        title="Long Data Sheet",
        status="approved",
        content={"columns": columns, "rowCount": 40},
        printLayout={"orientation": "landscape"},
    )
    service = V2PrintableLessonKitService(repos)
    story = service._material_story(
        long_sheet,
        package,
        service._styles(),
        usable_width=9.9 * 72,
    )
    body = service._render_story(story, (792, 612), long_sheet.title)
    reader = PdfReader(BytesIO(body))
    pages_with_header = sum(
        "Opportunity" in (page.extract_text() or "") for page in reader.pages
    )

    assert len(reader.pages) >= 3
    assert pages_with_header == len(reader.pages)


def test_three_short_scenarios_paginate_two_then_one():
    repos, package = n482_runtime()
    source = next(item for item in package.materials if item.type == "scenario_cards")
    scenarios = [
        {
            "context": f"Context {index}",
            "triggerOrTransition": "A short transition",
            "visualCue": "Show the card",
            "teacherWording": "Break, please",
            "learnerOpportunity": "Respond",
            "waitTimeSeconds": 5,
            "promptSequence": ["wait", "point"],
            "acceptedModalities": ["speech", "AAC"],
            "breakOutcome": "Honor the break",
            "returnSupport": "Check First–Then",
            "generalizationLabel": f"Practice {index}",
        }
        for index in range(1, 4)
    ]
    material = GeneratedMaterialDto(
        id="short-scenarios",
        packageId=package.id,
        type="scenario_cards",
        title="Short Scenario Cards",
        status="approved",
        content={"scenarios": scenarios},
        printLayout={"orientation": "landscape"},
    )
    service = V2PrintableLessonKitService(repos)
    story = service._material_story(
        material, package, service._styles(), usable_width=9.9 * 72
    )
    reader = PdfReader(
        BytesIO(service._render_story(story, (792, 612), material.title))
    )

    assert len(reader.pages) == 2
    assert "Context 1" in (reader.pages[0].extract_text() or "")
    assert "Context 2" in (reader.pages[0].extract_text() or "")
    assert "Context 3" in (reader.pages[1].extract_text() or "")


def test_scenario_response_modes_and_generalization_are_teacher_readable():
    repos, package = n482_runtime()
    material = next(item for item in package.materials if item.type == "scenario_cards")
    service = V2PrintableLessonKitService(repos)
    story = service._material_story(material, package, service._styles())
    text = " ".join(
        (page.extract_text() or "")
        for page in PdfReader(
            BytesIO(service._render_story(story, (612, 792), material.title))
        ).pages
    )

    assert "Accepted response: speech or AAC" in text
    assert "Accepted response: speech -> AAC" not in text
    assert "Generalization: Generalization:" not in text


def test_data_sheet_rows_match_lesson_spec_opportunity_budget():
    repos, package = n482_runtime()
    material = next(item for item in package.materials if item.type == "data_sheet")
    service = V2PrintableLessonKitService(repos)
    story = service._material_story(material, package, service._styles())
    table = next(item for item in story if isinstance(item, Table))
    expected = package.lessonSpec.goal.success_criterion.total_opportunities

    assert table._nrows == expected + 1


def test_legacy_package_complete_inventory_is_preserved_and_stably_ordered():
    repos = V2Repositories()
    package, package_materials = _seed_package(repos)
    service = V2PrintableLessonKitService(repos)

    resolved = service._resolve_current_package_materials(
        package, [item.id for item in reversed(package_materials)]
    )

    assert [item.type for item in resolved] == [
        "visual_card",
        "token_board",
        "data_sheet",
    ]
