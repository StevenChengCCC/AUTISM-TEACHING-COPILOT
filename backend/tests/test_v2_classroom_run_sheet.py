from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from app.integrations.private_object_storage import LocalPrivateObjectStorage
from app.schemas.v2_dto import PrintableLessonKitRequest
from app.services.v2_classroom_run_sheet_service import V2ClassroomRunSheetService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from test_v2_print_package_composition import _approve_n482
from test_v2_printable_lesson_kit import _settings
from test_v2_semantic_revision import n482_runtime


def _normalized_pdf_text(reader: PdfReader) -> str:
    return " ".join(
        "\n".join(page.extract_text() or "" for page in reader.pages).split()
    )


def test_run_sheet_projects_rich_steps_prep_materials_data_and_closeout():
    repos, package = n482_runtime()
    first = package.materials[0]
    assert first.specification is not None
    prepared = first.model_copy(
        update={
            "specification": first.specification.model_copy(
                update={
                    "printPreparation": [
                        "Check margins",
                        "Cut apart the three station cards",
                        "Print at actual size",
                        "Print at actual size",
                    ]
                }
            )
        }
    )
    step = package.teachingFlow[0].model_copy(
        update={
            "teacherScript": 'Say, "The route is ready."',
            "teacherAction": "Point to the first station and place the break card within reach.",
            "expectedLearnerResponse": "Orients to the station or requests a break by speech or AAC.",
            "waitTime": "5 seconds",
            "promptAction": "Wait, then point; fade the point after an independent response.",
            "reinforcementAction": "Acknowledge the response and honor a requested break.",
            "errorCorrectionAction": "Respond neutrally, represent the card, and offer another opportunity.",
            "dataToRecord": ["response mode", "prompt level", "latency"],
            "transitionCue": "Show the next station card.",
            "breakOption": "Accept speech or AAC and begin the two-minute break.",
        }
    )
    updated = package.model_copy(
        update={
            "materials": [prepared, *package.materials[1:]],
            "teachingFlow": [step, *package.teachingFlow[1:]],
            "preparationChecklist": [
                "Place the Break Card within reach",
                "Place the Break Card within reach",
                "Check margins",
            ],
            "documentContent": {
                **package.documentContent,
                "materialsNeeded": "Teacher-edited: route board, Break Card, data sheet, pencil",
                "dataCollectionPlan": "Teacher-edited: record response mode, prompt level, and latency for each valid opportunity.",
            },
        }
    )

    sheet = V2ClassroomRunSheetService().build(
        updated, updated.materials, learner_code="N-482"
    )

    assert sheet.learnerCode == "N-482"
    assert sheet.communicationModes == ["speech", "AAC"]
    assert sheet.materialsSource == "teacher_edit"
    assert sheet.materialsNeeded == [
        "Teacher-edited: route board, Break Card, data sheet, pencil"
    ]
    assert sheet.beforeClassChecklist.count("Place the Break Card within reach") == 1
    assert sheet.beforeClassChecklist.count("Print at actual size") == 1
    assert "Cut apart the three station cards" in sheet.beforeClassChecklist
    assert all("margin" not in item.casefold() for item in sheet.beforeClassChecklist)
    assert any(
        "goal-specific data sheet" in item.casefold()
        for item in sheet.beforeClassChecklist
    )
    assert any(
        "set first" in item.casefold() and "then" in item.casefold()
        for item in sheet.beforeClassChecklist
    )
    assert any(
        "5 bus tokens" in item.casefold()
        for item in sheet.beforeClassChecklist
    )
    assert sheet.steps[0].teacherScript == 'Say, "The route is ready."'
    assert sheet.steps[0].expectedLearnerResponse.startswith("Orients to the station")
    assert sheet.steps[0].waitTime == "5 seconds"
    assert sheet.steps[0].dataToRecord == ["response mode", "prompt level", "latency"]
    assert sheet.steps[0].breakOption
    assert sheet.dataReminder == [
        "Teacher-edited: record response mode, prompt level, and latency for each valid opportunity."
    ]
    assert any("invalid opportunities" in item for item in sheet.closeout)
    assert any("teacher's own words" in item for item in sheet.closeout)
    assert sheet.teacherJudgmentNote.startswith("Teacher judgment overrides this guide")


def test_materials_needed_falls_back_to_current_included_material_titles():
    _repos, package = n482_runtime()
    without_override = package.model_copy(
        update={
            "documentContent": {
                key: value
                for key, value in package.documentContent.items()
                if key != "materialsNeeded"
            }
        }
    )

    sheet = V2ClassroomRunSheetService().build(
        without_override, without_override.materials, learner_code="N-482"
    )

    assert sheet.materialsSource == "included_materials"
    assert sheet.materialsNeeded == [item.title for item in without_override.materials]


def test_complete_pdf_contains_run_sheet_current_revisions_edits_and_no_sensitive_text(tmp_path):
    repos, approved = _approve_n482()
    first_step = approved.teachingFlow[0].model_copy(
        update={
            "teacherScript": 'Say, "Break, please is available."',
            "expectedLearnerResponse": "Requests by speech or AAC, or continues the station activity.",
            "waitTime": "5 seconds",
            "promptAction": "Wait, point, then fade the point on the next stable opportunity.",
            "reinforcementAction": "Honor the break request and acknowledge the communication.",
            "errorCorrectionAction": "Use a neutral correction and offer another opportunity.",
            "dataToRecord": ["independent response", "prompt level", "break and return"],
            "transitionCue": "Show the next station card before moving.",
            "breakOption": "Accept speech or AAC; provide the two-minute break.",
        }
    )
    package = approved.model_copy(
        update={
            "teachingFlow": [first_step, *approved.teachingFlow[1:]],
            "preparationChecklist": [
                *approved.preparationChecklist,
                "Cut apart the station cards before class",
            ],
            "documentContent": {
                **approved.documentContent,
                "materialsNeeded": "Teacher-edited route board, Break Card, five bus tokens, timer, and data sheet",
                "dataCollectionPlan": "Record independent and prompted requests, response mode, latency, and return after a break.",
                "learnerName": "Jordan Example",
                "rawRecordText": "PRIVATE RAW RECORD EXCERPT",
            },
        }
    )
    package = repos.lesson_packages.save(
        package.model_copy(update={"validatedRevision": package.version + 1})
    )
    config = _settings(tmp_path)
    storage = LocalPrivateObjectStorage(config)
    service = V2PrintableLessonKitService(repos, storage, config)

    artifact = service.create_artifact(
        package.id,
        PrintableLessonKitRequest(
            materialIds=[item.id for item in package.materials],
            pageSize="Letter",
            reviewedConfirmation=True,
        ),
    )
    job = repos.export_jobs.get(artifact.artifactId)
    body = storage.read_bytes(job.storageObjectKey, config.MAX_EXPORT_BYTES)
    reader = PdfReader(BytesIO(body))
    text = _normalized_pdf_text(reader)

    for phrase in (
        "Classroom Run Sheet",
        "Teacher-edited route board, Break Card, five bus tokens, timer, and data sheet",
        'Say, "Break, please is available."',
        "Requests by speech or AAC",
        "5 seconds",
        "Wait, point, then fade the point",
        "Honor the break request",
        "neutral correction",
        "independent response, prompt level, break and return",
        "Show the next station card before moving",
        "provide the two-minute break",
        "Record independent and prompted requests",
        "Two-minute closeout",
        "invalid opportunities",
        "teacher's own words",
        "Teacher judgment overrides this guide",
    ):
        assert phrase.casefold() in text.casefold()
    assert "Jordan Example" not in text
    assert "PRIVATE RAW RECORD EXCERPT" not in text
    assert body.startswith(b"%PDF-") and len(body) > 0
    assert artifact.materialRevisions == {
        item.id: item.materialSpec.revision for item in package.materials
    }
    page_text = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    run_sheet_page = next(
        index
        for index, value in enumerate(page_text)
        if "Classroom Run Sheet" in value and "A compact guide for preparation" in value
    )
    first_material_page = next(
        index
        for index, value in enumerate(page_text)
        if index > run_sheet_page and "Complete the Blue Line" in value
    )
    # Standard text keeps the operational guide to at most two pages without
    # shrinking classroom-facing text.
    assert 1 <= first_material_page - run_sheet_page <= 2
    download = service.create_download(artifact.artifactId)
    assert download.downloadUrl
    assert repos.export_jobs.get(artifact.artifactId).downloadCount == 2


def test_renderer_version_prevents_reusing_pre_run_sheet_pdf(tmp_path):
    repos, package = _approve_n482()
    config = _settings(tmp_path)
    service = V2PrintableLessonKitService(
        repos, LocalPrivateObjectStorage(config), config
    )
    request = PrintableLessonKitRequest(
        materialIds=[item.id for item in package.materials],
        pageSize="Letter",
        reviewedConfirmation=True,
    )
    first = service.create_artifact(package.id, request)
    job = repos.export_jobs.get(first.artifactId)
    repos.export_jobs.save(
        job.model_copy(
            update={
                "printPackageManifest": job.printPackageManifest.model_copy(
                    update={"rendererVersion": "print-package-reportlab-v1"}
                )
            }
        )
    )

    second = service.create_artifact(package.id, request)

    assert second.artifactId != first.artifactId
    assert second.reused is False
    assert second.materialRevisions == first.materialRevisions
