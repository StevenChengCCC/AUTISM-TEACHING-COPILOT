from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api.v2_routes import _print_preset_service
from app.main import app
from app.core.exceptions import ConflictError, ValidationError
from app.integrations.private_object_storage import LocalPrivateObjectStorage
from app.schemas.v2_dto import PrintableLessonKitRequest
from app.services.v2_print_preset_service import V2PrintPresetService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from test_v2_print_package_composition import _approve_n482
from test_v2_printable_lesson_kit import _settings


EXPECTED_TYPES = {
    "complete_kit": {
        "blue_line_activity", "break_card", "first_then_board", "token_board",
        "visual_timer", "teacher_cue_card", "scenario_cards", "data_sheet",
        "summary_template",
    },
    "teacher_desk": {"teacher_cue_card", "data_sheet", "summary_template"},
    "classroom_materials": {
        "blue_line_activity", "break_card", "first_then_board", "token_board",
        "visual_timer", "scenario_cards",
    },
    "data_and_closeout": {"data_sheet", "summary_template"},
}


def _request(preset: str, page_size: str = "Letter"):
    return PrintableLessonKitRequest(
        materialIds=[], printPreset=preset, pageSize=page_size,
        reviewedConfirmation=True,
    )


def test_catalog_and_resolver_expose_only_four_fixed_inventories():
    repos, package = _approve_n482()
    service = V2PrintPresetService(repos)
    catalog = service.catalog(package.id, page_size="Letter")

    assert [item.printPreset for item in catalog.presets] == [
        "complete_kit", "teacher_desk", "classroom_materials", "data_and_closeout"
    ]
    assert catalog.presets[0].isDefault is True
    assert [item.estimatedPageCount for item in catalog.presets] == [18, 6, 9, 2]
    for preview in catalog.presets:
        resolution = service.resolve(package, preview.printPreset)
        assert {item.type for item in resolution.materials} == EXPECTED_TYPES[preview.printPreset]
        assert preview.available is True
        assert preview.estimatedPageCount > 0
        assert all(item.reason for item in preview.includedEntries)
        assert all(item.reason for item in preview.excludedEntries)


def test_catalog_api_exposes_letter_and_a4_without_creating_an_artifact():
    repos, package = _approve_n482()
    app.dependency_overrides[_print_preset_service] = lambda: V2PrintPresetService(repos)
    try:
        response = TestClient(app).get(
            f"/api/v2/lesson-packages/{package.id}/print-presets?pageSize=A4"
        )
        assert response.status_code == 200
        assert response.json()["pageSize"] == "A4"
        assert response.json()["textProfile"] == "standard"
        assert len(response.json()["presets"]) == 4
        assert repos.export_jobs.list() == []
    finally:
        app.dependency_overrides.pop(_print_preset_service, None)


def test_catalog_estimates_large_print_without_changing_preset_inventory():
    repos, package = _approve_n482()
    service = V2PrintPresetService(repos)
    standard = service.catalog(
        package.id, page_size="Letter", text_profile="standard"
    )
    large = service.catalog(
        package.id, page_size="Letter", text_profile="large"
    )
    assert large.textProfile == "large"
    assert [item.estimatedPageCount for item in large.presets] == [20, 8, 9, 4]
    assert [
        [entry.entryId for entry in item.includedEntries]
        for item in standard.presets
    ] == [
        [entry.entryId for entry in item.includedEntries]
        for item in large.presets
    ]


def test_arbitrary_material_subset_cannot_bypass_preset_inventory():
    repos, package = _approve_n482()
    with pytest.raises(ValidationError) as error:
        V2PrintPresetService(repos).resolve(
            package, "teacher_desk", [package.materials[0].id]
        )
    assert error.value.payload["disallowedMaterialIds"]
    assert error.value.payload["missingMaterialIds"]


def test_teacher_desk_remains_available_when_optional_teacher_guide_is_absent():
    repos, package = _approve_n482()
    without_guide = package.model_copy(update={
        "id": "package-without-optional-guide",
        "packageContentPlan": None,
        "materials": [item for item in package.materials if item.type != "teacher_cue_card"],
    })
    result = V2PrintPresetService(repos).resolve(without_guide, "teacher_desk")
    assert result.available is True
    assert {item.type for item in result.materials} == {"data_sheet", "summary_template"}


def test_unknown_material_type_is_not_assumed_to_be_learner_facing():
    repos, package = _approve_n482()
    unknown = package.materials[0].model_copy(update={
        "id": "teacher-worklog-unknown",
        "type": "teacher_worklog_unknown",
        "title": "Internal teacher worklog",
    })
    legacy = package.model_copy(update={
        "id": "package-with-unknown-type",
        "packageContentPlan": None,
        "materials": [*package.materials, unknown],
    })
    result = V2PrintPresetService(repos).resolve(legacy, "classroom_materials")
    assert unknown.id not in {item.id for item in result.materials}
    assert unknown.id in {item.entryId for item in result.excluded_entries}


@pytest.mark.parametrize("page_size", ["Letter", "A4"])
def test_each_preset_is_valid_revision_current_and_idempotently_separate(tmp_path, page_size):
    repos, package = _approve_n482()
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)
    artifact_ids: set[str] = set()

    for preset, expected_types in EXPECTED_TYPES.items():
        first = service.create_artifact(package.id, _request(preset, page_size))
        second = service.create_artifact(package.id, _request(preset, page_size))
        job = repos.export_jobs.get(first.artifactId)
        manifest = job.printPackageManifest
        body = storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
        assert body.startswith(b"%PDF-")
        assert len(PdfReader(BytesIO(body)).pages) == first.pageCount
        assert first.manifestVersion == 2
        assert first.printPreset == preset
        assert first.pageSize == ("A4" if page_size == "A4" else "LETTER")
        assert set(manifest.materialRevisions) == {
            item.id for item in package.materials if item.type in expected_types
        }
        assert manifest.sourceApprovalReadinessEvidence.ready is True
        assert manifest.packageRevision == package.version
        assert manifest.lessonSpecRevision == package.lessonSpec.revision
        assert all(section.includedReason for section in manifest.sections)
        assert all(item.reason for item in manifest.excludedEntries)
        assert second.reused is True and second.artifactId == first.artifactId
        assert first.artifactId not in artifact_ids
        artifact_ids.add(first.artifactId)


def test_every_preset_fails_closed_when_package_readiness_is_blocked(tmp_path):
    repos, package = _approve_n482()
    repos.lesson_packages.save(package.model_copy(update={"status": "teacher_review_needed"}))
    service = V2PrintableLessonKitService(
        repos, LocalPrivateObjectStorage(_settings(tmp_path)), _settings(tmp_path)
    )
    for preset in EXPECTED_TYPES:
        with pytest.raises(ConflictError):
            service.create_artifact(package.id, _request(preset))


def test_teacher_desk_preserves_teacher_materials_override_and_privacy(tmp_path):
    repos, package = _approve_n482()
    edited = package.model_copy(update={
        "validatedRevision": package.version + 1,
        "documentContent": {
            **package.documentContent,
            "materialsNeeded": "Teacher-edited route board, Break Card, five bus tokens, timer, and data sheet",
        }
    })
    repos.lesson_packages.save(edited)
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)
    artifact = service.create_artifact(edited.id, _request("teacher_desk"))
    job = repos.export_jobs.get(artifact.artifactId)
    text = " ".join(
        page.extract_text() or ""
        for page in PdfReader(BytesIO(storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES))).pages
    )
    assert "Teacher-edited route board" in text
    assert "N-482" in text
    assert "raw learner record" not in text.casefold()
    assert "source excerpt" not in text.casefold()
