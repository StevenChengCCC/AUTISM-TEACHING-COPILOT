from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from pypdf import PdfReader

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.api.v2_routes import _synthetic_n482_fixture_service
from app.main import app
from app.integrations.private_object_storage import LocalPrivateObjectStorage
from app.schemas.v2_dto import PrintableLessonKitRequest
from app.services.v2_print_layout_policy import (
    normalize_print_text,
    print_layout_policy,
)
from app.services.v2_print_preset_service import V2PrintPresetService
from app.services.v2_printable_lesson_kit_service import (
    V2PrintableLessonKitService,
)
from app.services.v2_repositories import V2Repositories
from app.services.v2_synthetic_n482_fixture_service import (
    V2SyntheticN482FixtureService,
)
from test_v2_print_package_composition import _approve_n482
from test_v2_printable_lesson_kit import _settings


PRESETS = (
    "complete_kit",
    "teacher_desk",
    "classroom_materials",
    "data_and_closeout",
)


def _request(preset: str, page_size: str, text_profile: str):
    return PrintableLessonKitRequest(
        materialIds=[],
        printPreset=preset,
        pageSize=page_size,
        textProfile=text_profile,
        reviewedConfirmation=True,
    )


def test_text_profile_schema_default_policy_and_ascii_normalization():
    assert PrintableLessonKitRequest(
        pageSize="Letter", reviewedConfirmation=True
    ).textProfile == "standard"
    assert _request("teacher_desk", "A4", "large").textProfile == "large"
    with pytest.raises(PydanticValidationError):
        _request("teacher_desk", "A4", "extra_large")

    standard = print_layout_policy("standard")
    large = print_layout_policy("large")
    assert standard.safe_margin_inches >= 0.5
    assert large.teacher_body_points >= 12
    assert large.teacher_compact_points >= 11
    assert large.teacher_data_header_points >= 10
    assert large.learner_label_points >= 26
    assert large.learner_primary_points >= 34
    assert large.preserve_image_aspect_ratio is True
    assert large.repeat_table_headers is True
    assert large.color_only_signals_allowed is False
    assert normalize_print_text("First–Then → choice • item □") == (
        "First-Then -> choice - item [ ]"
    )


def test_n482_all_preset_page_and_text_combinations_are_distinct_and_parseable(
    tmp_path,
):
    repos, package = _approve_n482()
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)
    artifact_ids: set[str] = set()
    hashes: set[str] = set()

    for preset in PRESETS:
        for page_size in ("Letter", "A4"):
            for text_profile in ("standard", "large"):
                request = _request(preset, page_size, text_profile)
                first = service.create_artifact(package.id, request)
                second = service.create_artifact(package.id, request)
                job = repos.export_jobs.get(first.artifactId)
                body = storage.read_bytes(
                    job.storageObjectKey, config.MAX_EXPORT_BYTES
                )
                reader = PdfReader(BytesIO(body))

                assert body.startswith(b"%PDF-")
                assert len(body) > 0
                assert len(reader.pages) == first.pageCount
                assert first.textProfile == text_profile
                assert job.printPackageManifest.textProfile == text_profile
                assert job.printPackageManifest.pageCount == first.pageCount
                assert page_size.casefold() in first.filename.casefold()
                assert text_profile in first.filename
                assert second.reused is True
                assert second.artifactId == first.artifactId
                assert first.artifactId not in artifact_ids
                assert first.sha256 not in hashes
                artifact_ids.add(first.artifactId)
                hashes.add(first.sha256)

                expected_width = 595 if page_size == "A4" else 612
                portrait_pages = [
                    page
                    for page in reader.pages
                    if float(page.mediabox.height) > float(page.mediabox.width)
                ]
                if portrait_pages:
                    assert abs(float(portrait_pages[0].mediabox.width) - expected_width) < 1


def _stress_package(repos, package):
    expansion = (
        "translated expanded classroom wording with additional explicit context "
        "for clear preparation and consistent teacher interpretation"
    )
    steps = []
    for index in range(8):
        source = package.teachingFlow[index % len(package.teachingFlow)]
        steps.append(source.model_copy(update={
            "id": f"stress-step-{index + 1}",
            "title": f"Step {index + 1}: {expansion}",
            "description": f"{source.description} {expansion}.",
            "teacherAction": f"{source.teacherAction} {expansion}; keep the direction neutral and observable.",
            "teacherScript": f"{source.teacherScript or 'Show the support and pause.'} {expansion}.",
            "expectedLearnerResponse": f"{source.expectedLearnerResponse} during {expansion}.",
            "promptAction": f"Wait five seconds, then use the visual or gestural cue, model once, and use the brief verbal cue only if needed; {expansion}.",
            "errorCorrectionAction": f"Respond neutrally, represent the opportunity without pressure, and pause when needed; {expansion}.",
            "transitionCue": f"Use the current First-Then board and preview {expansion}.",
            "breakOption": f"Honor the break or stop response and use the visible timer; {expansion}.",
        }))

    changed_materials = []
    for material in package.materials:
        title = f"{material.title} - {expansion.title()}"
        spec = material.materialSpec
        if spec is not None and material.type == "data_sheet":
            spec = spec.model_copy(update={"title": title, "content": spec.content.model_copy(update={
                "exact_columns": [
                    "opportunity number and translated context label",
                    "complete transition or activity context description",
                    "observed response outcome after the full processing interval",
                    "independence status using the current operational definition",
                    "least intrusive prompt level actually used during this opportunity",
                    "latency in seconds after the naturally occurring instructional cue",
                    "accepted communication mode used by the learner",
                    "break requested delivered honored and return status",
                ],
                "prompt_level_definitions": [
                    f"Definition {index + 1}: {expansion}; record only the support actually observed and never infer a prompt level."
                    for index in range(6)
                ],
                "trial_definition": f"{spec.content.trial_definition} {expansion}.",
                "independence_rule": f"{spec.content.independence_rule} {expansion}.",
            })})
        elif spec is not None and material.type == "scenario_cards":
            scenarios = [
                item.model_copy(update={
                    "context": f"{item.context} - {expansion}",
                    "trigger_or_transition": f"{item.trigger_or_transition}; {expansion}",
                    "visual_cue": f"{item.visual_cue} {expansion}.",
                    "teacher_wording": f"{item.teacher_wording} {expansion}.",
                    "return_support": f"{item.return_support} {expansion}.",
                })
                for item in spec.content.scenarios
            ]
            spec = spec.model_copy(update={
                "title": title,
                "content": spec.content.model_copy(update={"scenarios": scenarios}),
            })
        elif spec is not None and material.type in {
            "teacher_cue_card", "summary_template"
        }:
            spec = spec.model_copy(update={"title": title, "content": spec.content.model_copy(update={
                "prompts_used": [
                    f"Prompt hierarchy {index + 1}: {expansion}; wait, fade, and preserve teacher judgment."
                    for index in range(7)
                ],
                "reporting_fields": [
                    f"Expanded reporting field {index + 1}: {expansion}"
                    for index in range(8)
                ],
                "regulation_and_break_notes": f"{spec.content.regulation_and_break_notes} {expansion}.",
            })})
        elif spec is not None:
            spec = spec.model_copy(update={"title": title})

        specification = material.specification
        if specification is not None:
            specification = specification.model_copy(update={
                "print_preparation": [
                    f"Preparation action {index + 1}: {expansion}."
                    for index in range(5)
                ],
                "teacher_directions": [
                    f"Teacher direction {index + 1}: {expansion}."
                    for index in range(4)
                ],
            })
        changed = material.model_copy(update={
            "title": title,
            "materialSpec": spec,
            "specification": specification,
        })
        stored = repos.generated_materials.get(changed.id)
        repos.generated_materials.save(
            changed.model_copy(update={"version": stored.version})
        )
        changed_materials.append(changed)

    access_plan = package.lessonSpec.access_plan.model_copy(update={
        "layout_requirements": [f"Access requirement {index + 1}: {expansion}" for index in range(8)],
        "motor_access_alternatives": [f"Motor access alternative {index + 1}: {expansion}" for index in range(5)],
    })
    lesson_spec = package.lessonSpec.model_copy(update={"access_plan": access_plan})
    return package.model_copy(update={
        "teachingFlow": steps,
        "materials": changed_materials,
        "lessonSpec": lesson_spec,
        "documentContent": {
            **package.documentContent,
            "materialsNeeded": "; ".join(
                f"Teacher-edited setup item {index + 1}: {expansion}"
                for index in range(12)
            ),
        },
    })


def test_combined_long_content_and_translation_stress_matrix_has_no_text_overflow(
    tmp_path,
):
    repos, approved = _approve_n482()
    package = _stress_package(repos, approved)
    config = _settings(tmp_path)
    service = V2PrintableLessonKitService(
        repos, LocalPrivateObjectStorage(config), config
    )
    preset_service = V2PrintPresetService(repos)
    rendered = 0

    for preset in PRESETS:
        resolution = preset_service.resolve(package, preset)
        for page_size in ("Letter", "A4"):
            for text_profile in ("standard", "large"):
                manifest = service.build_manifest(
                    package,
                    resolution.materials,
                    resolution=resolution,
                    print_preset=preset,
                    page_size=page_size,
                    text_profile=text_profile,
                )
                body = service._build_pdf(
                    package,
                    resolution.materials,
                    page_size,
                    manifest=manifest,
                )
                assert body.startswith(b"%PDF-")
                reader = PdfReader(BytesIO(body))
                assert len(reader.pages) >= resolution.estimated_page_count
                extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
                assert "translated expanded classroom wording" in extracted
                assert not any(char in extracted for char in "–—‑→•□")
                for page in reader.pages:
                    assert float(page.mediabox.left) == 0
                    assert float(page.mediabox.bottom) == 0
                    assert float(page.mediabox.width) > 0
                    assert float(page.mediabox.height) > 0
                rendered += 1
    assert rendered == 16


def test_synthetic_n482_fixture_is_resettable_stable_and_production_guarded():
    repos = V2Repositories()
    service = V2SyntheticN482FixtureService(
        repos, Settings(APP_ENV="development")
    )
    first = service.reset()
    second = service.reset()
    assert first["fixtureId"] == second["fixtureId"]
    assert first["learnerId"] == second["learnerId"] == "synthetic-n482"
    assert first["packageId"] == second["packageId"]
    assert first["sessionId"] == second["sessionId"]
    assert first["synthetic"] is True
    assert len([
        item for item in repos.learners.list() if item.id == "synthetic-n482"
    ]) == 1
    package = repos.lesson_packages.get(first["packageId"])
    assert package.status == "approved"
    assert all(item.status == "approved" for item in package.materials)
    jobs = [
        item
        for item in repos.generation_jobs.list()
        if item.packageId == package.id
    ]
    assert len(jobs) == 1
    assert jobs[0].status == "completed"
    assert all(
        not str(value).startswith("/storage/")
        for material in package.materials
        for value in material.content.values()
        if isinstance(value, str) and "image" in value.casefold()
    )

    with pytest.raises(NotFoundError):
        V2SyntheticN482FixtureService(
            repos, Settings(APP_ENV="production")
        ).reset()


def test_synthetic_n482_reset_api_uses_normal_authenticated_dev_route():
    repos = V2Repositories()
    service = V2SyntheticN482FixtureService(
        repos, Settings(APP_ENV="development")
    )
    app.dependency_overrides[_synthetic_n482_fixture_service] = lambda: service
    try:
        response = TestClient(app).post("/api/v2/dev/fixtures/n482/reset")
        assert response.status_code == 200
        assert response.json()["synthetic"] is True
        assert response.json()["packageId"] == "synthetic-n482-package-1"
    finally:
        app.dependency_overrides.pop(_synthetic_n482_fixture_service, None)
