from __future__ import annotations

import re
from typing import Iterable

from app.schemas.v2_dto import (
    ClassroomRunSheetDto,
    ClassroomRunSheetStepDto,
    GeneratedMaterialDto,
    LessonPackageDto,
)


class V2ClassroomRunSheetService:
    """Project approved package data into a compact classroom operating guide."""

    teacher_judgment_note = (
        "Teacher judgment overrides this guide. Pause, adapt, or stop when the "
        "learner's communication, regulation, access, or safety needs require it."
    )
    _generic_prep_noise = {
        "check margins",
        "check print margins",
        "review wording",
        "review at actual size",
        "review at actual size before printing",
    }

    def build(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        *,
        learner_code: str,
    ) -> ClassroomRunSheetDto:
        spec = package.lessonSpec
        communication_modes = self._dedupe(
            (
                spec.communication_plan.accepted_modes
                if spec and spec.communication_plan.accepted_modes
                else (
                    spec.goal.accepted_response_modes
                    if spec
                    else self._split_text(package.responseModality)
                )
            )
        )
        success_criterion = self._success_criterion(package)
        before_class = self._before_class(package, materials)
        materials_needed, materials_source = self._materials_needed(package, materials)
        steps = [
            ClassroomRunSheetStepDto(
                id=step.id,
                title=step.title,
                duration=step.duration,
                teacherScript=self._clean(step.teacherScript) or None,
                teacherAction=self._clean(step.teacherAction),
                expectedLearnerResponse=(
                    self._clean(step.expectedLearnerResponse)
                    or self._clean(step.learnerAction)
                ),
                waitTime=self._clean(step.waitTime),
                promptAction=self._clean(step.promptAction),
                reinforcementAction=self._clean(step.reinforcementAction),
                errorCorrectionAction=self._clean(step.errorCorrectionAction),
                dataToRecord=self._dedupe(step.dataToRecord),
                transitionCue=self._clean(step.transitionCue),
                breakOption=self._clean(step.breakOption) or None,
            )
            for step in package.teachingFlow
        ]
        return ClassroomRunSheetDto(
            learnerCode=self._safe_code(learner_code),
            goal=self._clean(
                str((package.documentContent or {}).get("goal") or package.goal)
            ),
            totalDuration=package.duration,
            communicationModes=communication_modes,
            successCriterion=success_criterion,
            beforeClassChecklist=before_class,
            materialsNeeded=materials_needed,
            materialsSource=materials_source,
            steps=steps,
            dataReminder=self._data_reminder(package),
            closeout=self._closeout(package),
            teacherJudgmentNote=self.teacher_judgment_note,
        )

    def _before_class(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
    ) -> list[str]:
        values = [*package.preparationChecklist]
        for material in materials:
            if material.specification is not None:
                values.extend(material.specification.printPreparation)
        return [
            value
            for value in self._dedupe(values)
            if self._key(value) not in self._generic_prep_noise
        ]

    def _materials_needed(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
    ) -> tuple[list[str], str]:
        edited = (package.documentContent or {}).get("materialsNeeded")
        if isinstance(edited, str) and edited.strip():
            return [edited.strip()], "teacher_edit"
        if isinstance(edited, list):
            values = self._dedupe(str(value) for value in edited if str(value).strip())
            if values:
                return values, "teacher_edit"
        return self._dedupe(item.title for item in materials), "included_materials"

    def _success_criterion(self, package: LessonPackageDto) -> str:
        value = self._clean(package.successCriterion)
        if value and "teacher-defined criterion required" not in value.casefold():
            return value
        criterion = package.lessonSpec.goal.success_criterion if package.lessonSpec else None
        if criterion and criterion.required_successful_opportunities and criterion.total_opportunities:
            text = (
                f"{criterion.required_successful_opportunities} successful opportunities "
                f"out of {criterion.total_opportunities}"
            )
            if criterion.maximum_prompt_level:
                text += f" at or below {criterion.maximum_prompt_level}"
            return text
        return "Use the current teacher-approved criterion and record the observed result."

    def _data_reminder(self, package: LessonPackageDto) -> list[str]:
        edited = (package.documentContent or {}).get("dataCollectionPlan")
        if isinstance(edited, str) and edited.strip():
            return [edited.strip()]
        spec = package.lessonSpec
        if spec is None:
            return [
                value
                for value in self._dedupe(
                    [package.observableResponse, package.successCriterion]
                )
                if value
            ]
        values: list[str] = []
        if spec.data_plan.measures:
            values.append("Record: " + "; ".join(spec.data_plan.measures))
        if spec.data_plan.trial_definition:
            values.append("Count a trial when: " + spec.data_plan.trial_definition)
        if spec.data_plan.independence_definition:
            values.append("Independent means: " + spec.data_plan.independence_definition)
        if spec.data_plan.prompt_levels:
            values.append("Prompt levels: " + ", ".join(spec.data_plan.prompt_levels))
        return self._dedupe(values)

    def _closeout(self, package: LessonPackageDto) -> list[str]:
        values = [
            "Record each trial outcome and mark invalid opportunities so they are excluded from numeric results.",
        ]
        spec = package.lessonSpec
        has_break = bool(
            (spec and (spec.transition_plan.break_request or spec.transition_plan.return_support))
            or any(step.breakOption for step in package.teachingFlow)
        )
        if has_break:
            values.append("Record break request, break delivery, and return when applicable.")
        has_prompt_data = bool(
            (spec and spec.data_plan.prompt_levels)
            or any(step.dataToRecord for step in package.teachingFlow)
        )
        if has_prompt_data:
            values.append("Record the prompt level used for each valid opportunity.")
        values.extend(
            [
                "Preserve observations in the teacher's own words; do not replace them with generated conclusions.",
                "Open Sessions and complete the existing session outcome flow before closing the lesson.",
            ]
        )
        return values

    @staticmethod
    def _clean(value: object) -> str:
        return " ".join(str(value or "").split())

    @classmethod
    def _key(cls, value: object) -> str:
        return re.sub(r"[^a-z0-9]+", " ", cls._clean(value).casefold()).strip()

    @classmethod
    def _dedupe(cls, values: Iterable[object]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = cls._clean(raw)
            key = cls._key(value)
            if value and key and key not in seen:
                result.append(value)
                seen.add(key)
        return result

    @staticmethod
    def _split_text(value: str) -> list[str]:
        return [item.strip() for item in re.split(r"[,;\n]", value or "") if item.strip()]

    @staticmethod
    def _safe_code(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
        return safe[:40] or "Learner"
