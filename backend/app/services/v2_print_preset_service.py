from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import NotFoundError, ValidationError
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    LessonPackageDto,
    PrintPreset,
    PrintPresetCatalog,
    PrintPresetInventoryEntry,
    PrintPresetPreview,
)
from app.services.v2_print_readiness_service import V2PrintReadinessService
from app.services.v2_repositories import V2Repositories, repositories


@dataclass(frozen=True)
class PrintPresetResolution:
    preset: PrintPreset
    display_name: str
    description: str
    materials: list[GeneratedMaterialDto]
    front_sections: list[str]
    included_reasons: dict[str, str]
    excluded_entries: list[PrintPresetInventoryEntry]
    estimated_page_count: int
    available: bool
    unavailable_reason: str | None


class V2PrintPresetService:
    """Resolve fixed print inventories without accepting arbitrary subsets."""

    presets: tuple[PrintPreset, ...] = (
        "complete_kit",
        "teacher_desk",
        "classroom_materials",
        "data_and_closeout",
    )
    _names = {
        "complete_kit": "Complete Kit",
        "teacher_desk": "Teacher Desk Copy",
        "classroom_materials": "Classroom Materials",
        "data_and_closeout": "Data & Closeout",
    }
    _descriptions = {
        "complete_kit": "The complete approved lesson package, including teacher front matter and every current material.",
        "teacher_desk": "A compact operational copy with the Classroom Run Sheet, data sheet, and included teacher reference or summary pages.",
        "classroom_materials": "Learner-facing activities, cards, boards, scenarios, schedules, and timers without teacher-only administration pages.",
        "data_and_closeout": "The current goal-specific data sheet, its coding definitions, and the included lesson summary or closeout page.",
    }
    _front_sections = {
        "complete_kit": ["cover", "personalization_summary", "teacher_brief", "lesson_flow"],
        "teacher_desk": ["lesson_flow"],
        "classroom_materials": [],
        "data_and_closeout": [],
    }
    _front_titles = {
        "cover": "Complete lesson kit",
        "personalization_summary": "Why this lesson is personalized",
        "teacher_brief": "Teacher lesson brief",
        "lesson_flow": "Classroom Run Sheet",
    }
    _teacher_guides = {"teacher_cue_card"}
    _data_types = {"data_sheet"}
    _summary_types = {"summary_template", "session_summary"}
    _teacher_only = _teacher_guides | _data_types | _summary_types | {"handoff_note"}
    _learner_facing = {
        "blue_line_activity", "quantity_cards", "number_cards", "matching_page",
        "sorting_page", "sequence_cards", "task_analysis_cards", "social_narrative",
        "visual_card", "break_card", "help_card", "first_then_board", "token_board",
        "visual_timer", "choice_board", "core_word_board", "emotion_scale",
        "visual_schedule", "scenario_cards",
    }
    _page_weights = {
        "blue_line_activity": 2,
        "scenario_cards": 3,
        "data_sheet": 1,
    }

    def __init__(self, repos: V2Repositories = repositories) -> None:
        self.repos = repos

    @staticmethod
    def _revision(material: GeneratedMaterialDto) -> int:
        return material.materialSpec.revision if material.materialSpec else material.version

    def resolve(
        self,
        package: LessonPackageDto,
        preset: PrintPreset,
        requested_material_ids: list[str] | None = None,
    ) -> PrintPresetResolution:
        current = V2PrintReadinessService(self.repos).current_materials(package)
        if preset == "complete_kit":
            selected = list(current)
        elif preset == "teacher_desk":
            selected = [
                item for item in current
                if item.type in self._data_types | self._teacher_guides | self._summary_types
            ]
        elif preset == "classroom_materials":
            selected = [item for item in current if item.type in self._learner_facing]
        else:
            selected = [
                item for item in current
                if item.type in self._data_types | self._summary_types
            ]

        expected_ids = {item.id for item in selected}
        requested_ids = set(requested_material_ids or [])
        if requested_ids and requested_ids != expected_ids:
            raise ValidationError(
                "Material IDs must match the deterministic inventory for the selected print preset.",
                payload={
                    "printPreset": preset,
                    "missingMaterialIds": sorted(expected_ids - requested_ids),
                    "disallowedMaterialIds": sorted(requested_ids - expected_ids),
                },
            )

        missing: list[str] = []
        if preset in {"teacher_desk", "data_and_closeout"} and not any(
            item.type in self._data_types for item in selected
        ):
            missing.append("a current goal-specific data sheet")
        if preset == "data_and_closeout" and not any(
            item.type in self._summary_types for item in selected
        ):
            missing.append("a current lesson summary or closeout page")
        if preset == "classroom_materials" and not selected:
            missing.append("at least one learner-facing classroom material")

        included_reasons = {
            item.id: self._material_inclusion_reason(preset, item) for item in selected
        }
        excluded = [
            PrintPresetInventoryEntry(
                entryType="material",
                entryId=item.id,
                title=item.title,
                materialType=item.type,
                revision=self._revision(item),
                reason=self._material_exclusion_reason(preset, item),
            )
            for item in current
            if item.id not in expected_ids
        ]
        selected_front = set(self._front_sections[preset])
        excluded.extend(
            PrintPresetInventoryEntry(
                entryType="section",
                entryId=section,
                title=title,
                reason=self._front_exclusion_reason(preset, section),
            )
            for section, title in self._front_titles.items()
            if section not in selected_front
        )
        front_pages = 0
        for section in self._front_sections[preset]:
            front_pages += 3 if section == "lesson_flow" else 1
        material_pages = sum(self._page_weights.get(item.type, 1) for item in selected)
        return PrintPresetResolution(
            preset=preset,
            display_name=self._names[preset],
            description=self._descriptions[preset],
            materials=selected,
            front_sections=list(self._front_sections[preset]),
            included_reasons=included_reasons,
            excluded_entries=excluded,
            estimated_page_count=max(1, front_pages + material_pages),
            available=not missing,
            unavailable_reason=("This preset requires " + " and ".join(missing) + ".") if missing else None,
        )

    def catalog(
        self,
        package_id: str,
        *,
        page_size: str,
        text_profile: str = "standard",
    ) -> PrintPresetCatalog:
        package = self.repos.lesson_packages.get(package_id)
        if not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        previews: list[PrintPresetPreview] = []
        for preset in self.presets:
            resolution = self.resolve(package, preset)
            included = [
                PrintPresetInventoryEntry(
                    entryType="section",
                    entryId=section,
                    title=self._front_titles[section],
                    reason=self._front_inclusion_reason(preset, section),
                )
                for section in resolution.front_sections
            ]
            included.extend(
                PrintPresetInventoryEntry(
                    entryType="material",
                    entryId=item.id,
                    title=item.title,
                    reason=resolution.included_reasons[item.id],
                    materialType=item.type,
                    revision=self._revision(item),
                )
                for item in resolution.materials
            )
            large_print_allowance = (
                2 if preset == "complete_kit"
                else 2 if preset in {"teacher_desk", "data_and_closeout"}
                else 0
            ) if text_profile == "large" else 0
            previews.append(PrintPresetPreview(
                printPreset=preset,
                displayName=resolution.display_name,
                description=resolution.description,
                isDefault=preset == "complete_kit",
                includedEntries=included,
                excludedEntries=resolution.excluded_entries,
                estimatedPageCount=(
                    resolution.estimated_page_count + large_print_allowance
                ),
                available=resolution.available,
                unavailableReason=resolution.unavailable_reason,
            ))
        return PrintPresetCatalog(
            packageId=package.id,
            packageRevision=package.version,
            pageSize="A4" if page_size == "A4" else "LETTER",
            textProfile="large" if text_profile == "large" else "standard",
            presets=previews,
        )

    def require_available(self, resolution: PrintPresetResolution) -> None:
        if not resolution.available:
            raise ValidationError(resolution.unavailable_reason or "The selected print preset is unavailable.")

    @classmethod
    def _front_inclusion_reason(cls, preset: PrintPreset, section: str) -> str:
        if preset == "complete_kit":
            return "Included in the complete approved lesson package."
        return "Included as the teacher's compact classroom operating guide."

    @classmethod
    def _front_exclusion_reason(cls, preset: PrintPreset, section: str) -> str:
        if preset == "teacher_desk":
            return "Omitted to keep the desk copy compact; the Classroom Run Sheet carries the operational guidance."
        if preset == "classroom_materials":
            return "Teacher-only front matter is excluded from the learner-facing classroom set."
        if preset == "data_and_closeout":
            return "Unrelated front matter is excluded from the focused data and closeout copy."
        return "No section is excluded from Complete Kit."

    @classmethod
    def _material_inclusion_reason(
        cls, preset: PrintPreset, material: GeneratedMaterialDto
    ) -> str:
        if preset == "complete_kit":
            return "Current approved material included in the complete package."
        if preset == "teacher_desk":
            if material.type in cls._data_types:
                return "Included for in-session goal data recording and coding definitions."
            if material.type in cls._teacher_guides:
                return "Included as the package's current teacher cue or prompting guide."
            return "Included for post-session summary and closeout."
        if preset == "classroom_materials":
            return "Included as a current approved learner-facing classroom support or activity."
        if material.type in cls._data_types:
            return "Included as the current goal-specific data sheet with coding definitions."
        return "Included as the current lesson summary or closeout page."

    @classmethod
    def _material_exclusion_reason(
        cls, preset: PrintPreset, material: GeneratedMaterialDto
    ) -> str:
        if preset == "teacher_desk":
            return "Learner-facing duplicate material is omitted from the compact teacher desk copy."
        if preset == "classroom_materials":
            return "Teacher-only data, summary, or prompting administration is excluded from classroom materials."
        if preset == "data_and_closeout":
            return "Unrelated learner-facing or teacher-guide material is excluded from the data and closeout copy."
        return "No approved material is excluded from Complete Kit."
