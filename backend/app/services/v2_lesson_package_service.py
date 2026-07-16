from __future__ import annotations

from app.core.config import Settings, settings
from app.core.exceptions import (
    AIInvalidOutputError,
    AIProviderFailureError,
    AppError,
    ConflictError,
    NotFoundError,
    SafetyDeferralError,
    ValidationError,
)
from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.schemas.v2_dto import (
    GeneratedMaterial,
    GeneratedMaterialDto,
    GenerationMetadataDto,
    DataSheetMaterialSpecification,
    DataSheetSpecificationDto,
    BreakCardSpecification,
    ChoiceBoardSpecification,
    ErrorCorrectionPlanDto,
    GeneralizationPlanDto,
    HelpCardSpecification,
    HandoffNoteSpecification,
    FirstThenBoardSpecification,
    LessonDesignDraft,
    LessonDesignDraftDto,
    LessonPackage,
    LessonPackageDto,
    LessonPackageDecisionRequest,
    LessonPackageRegenerateSectionRequest,
    LessonPackageUpdateRequest,
    LessonPackageVersionComparisonDto,
    LessonPackageVersionDto,
    PromptingPlanDto,
    PrintLayout,
    ReinforcementPlanDto,
    SessionSummarySpecification,
    ScenarioCardsSpecification,
    SortingPageSpecification,
    MatchingPageSpecification,
    TeachingStep,
    TeachingStepDto,
    TeacherAdaptationPlanDto,
    TeacherCueCardSpecification,
    TokenBoardSpecification,
    VisualCardSpecification,
)
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_image_asset_service import V2ImageAssetService
from app.services.v2_ai_context_service import (
    build_lesson_generation_context,
    build_image_generation_context,
    build_safe_image_prompt,
    personalization_sources,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_safety_harness_service import V2SafetyHarnessService
from app.services.v2_standards_skill_service import V2StandardsSkillService


class V2LessonPackageService:
    def __init__(
        self,
        repos: V2Repositories = repositories,
        ai: V2AIProvider | None = None,
        safety: V2SafetyHarnessService | None = None,
        standards: V2StandardsSkillService | None = None,
        images: V2ImageAssetService | None = None,
        config: Settings = settings,
    ):
        self.repos = repos
        self.ai = ai or get_v2_ai_provider()
        self.safety = safety or V2SafetyHarnessService()
        self.standards = standards or V2StandardsSkillService()
        self.images = images or V2ImageAssetService(repos, ai=self.ai)
        self.config = config
        self.learners = V2LearnerService(repos)

    def get(self, package_id: str) -> LessonPackage:
        package = self.repos.packages.get(package_id)
        if not package:
            raise NotFoundError("Lesson package not found")
        return package

    def generate(self, draft: LessonDesignDraft) -> LessonPackage:
        if not draft.goal_text or not draft.selected_materials:
            raise ValidationError(
                "Confirmed goal and materials are required before generation"
            )
        package_id = self.repos.next_id("package")
        lesson_brief = self.ai.polish_lesson_brief(draft)
        safety_report = self.safety.review(draft, lesson_brief)
        if not safety_report.passed:
            raise SafetyDeferralError(
                {
                    "message": "Lesson requires safety review before generation.",
                    "requires_bcba": True,
                    "checks": [
                        item.model_dump(mode="json", by_alias=True)
                        for item in safety_report.checks
                    ],
                }
            )
        standards_report = self.standards.evaluate(draft)
        materials = self._build_materials(package_id, draft.selected_materials)
        package = LessonPackage(
            id=package_id,
            learner_id=draft.learner_id,
            draft_id=draft.id,
            goal=draft.goal_text,
            duration=draft.duration,
            theme=draft.theme,
            lesson_brief=lesson_brief,
            teaching_flow=self._build_flow(),
            materials=materials,
            summary_template="Note what worked, prompt level, regulation, generalization, and next steps.",
            safety_report=safety_report,
            standards_report=standards_report,
        )
        with self.repos.transaction():
            package = self.repos.packages.save(package)
            for material in materials:
                self.repos.materials.save(material)
        return package

    def generate_product(self, draft: LessonDesignDraftDto) -> LessonPackageDto:
        """Run the product package pipeline through provider, safety, and skills."""

        if not draft.goalText.strip() or not draft.selectedMaterials:
            raise ValidationError(
                "Confirmed goal and materials are required before generation"
            )

        package_id = self.repos.next_id("package")
        learner = self.learners.get(draft.learnerId)
        learner_context = build_lesson_generation_context(learner, draft)
        provider_name = getattr(self.ai, "provider_name", self.ai.__class__.__name__)
        fallback_material_metadata = None
        try:
            generated_content = self.ai.generate_lesson_package(draft, learner_context)
            generation_metadata = getattr(self.ai, "last_generation_metadata", None)
            fallback_used = bool(getattr(self.ai, "last_fallback_used", False))
        except Exception as exc:
            if self.config.effective_ai_failure_mode != "mock_fallback":
                if isinstance(exc, AppError):
                    raise
                raise AIProviderFailureError(
                    "AI generation is temporarily unavailable. Please try again later."
                ) from exc
            from app.integrations.mock_ai_provider import MockV2AIProvider

            fallback_provider = MockV2AIProvider(config=self.config)
            generated_content = fallback_provider.generate_lesson_package(
                draft, learner_context
            )
            generation_metadata = fallback_provider.last_generation_metadata
            fallback_material_metadata = (
                fallback_provider.generation_metadata_by_skill.get(
                    "material_generation"
                )
            )
            if generation_metadata is not None:
                generation_metadata = generation_metadata.model_copy(
                    update={
                        "provider": provider_name,
                        "output_source": "mock_fallback",
                    }
                )
            if fallback_material_metadata is not None:
                fallback_material_metadata = fallback_material_metadata.model_copy(
                    update={
                        "provider": provider_name,
                        "output_source": "mock_fallback",
                    }
                )
            fallback_used = True
        fallback_content = self._fallback_product_content(draft, learner_context)
        material_generation_metadata = fallback_material_metadata or getattr(
            self.ai, "generation_metadata_by_skill", {}
        ).get("material_generation")
        if fallback_used and material_generation_metadata is None:
            material_generation_metadata = generation_metadata
        invalid_provider_output = provider_name != "mock" and (
            not self._is_valid_product_flow(generated_content.get("teachingFlow"))
            or not self._generated_materials_cover_draft(
                generated_content.get("materials"), draft
            )
        )
        is_real_provider_output = bool(
            generation_metadata and generation_metadata.output_source == "provider"
        )
        if invalid_provider_output and is_real_provider_output:
            raise AIInvalidOutputError(
                "AI returned an incomplete lesson package. Please retry."
            )
        if invalid_provider_output:
            fallback_used = True
        teaching_flow = self._parse_product_flow(
            generated_content.get("teachingFlow"), fallback_content["teachingFlow"]
        )
        teaching_flow = self._enrich_product_flow(teaching_flow, draft)
        materials = self._build_product_materials(
            package_id,
            draft,
            generated_content.get("materials"),
            fallback_content["materials"],
        )
        if material_generation_metadata is not None:
            metadata_dto = GenerationMetadataDto.model_validate(
                material_generation_metadata.model_dump(mode="json", by_alias=True)
            )
            materials = [
                material.model_copy(
                    update={
                        "generationStatus": material_generation_metadata.status,
                        "generationMetadata": metadata_dto,
                    }
                )
                for material in materials
            ]
        self._prepare_product_material_images(learner, materials)
        safety_review = self.safety.review_product(draft, generated_content)
        standards_checks = self.standards.evaluate_product(
            draft, materials, generated_content
        )
        package_status = (
            "safety_review_needed"
            if safety_review.status == "blocked"
            else (
                "validation_failed"
                if any(check.status == "blocked" for check in standards_checks)
                else "teacher_review_needed"
            )
        )

        package = LessonPackageDto(
            id=package_id,
            learnerId=draft.learnerId,
            draftId=draft.id,
            goal=draft.goalText,
            duration=draft.duration,
            theme=draft.theme,
            lessonBrief=generated_content.get("lessonBrief")
            or fallback_content["lessonBrief"],
            teachingFlow=teaching_flow,
            materials=materials,
            summaryTemplate=generated_content.get("summaryTemplate")
            or fallback_content["summaryTemplate"],
            safetyReview=safety_review,
            standardsChecks=standards_checks,
            aiProvider=provider_name,
            fallbackUsed=fallback_used,
            generationStatus=(
                generation_metadata.status if generation_metadata else None
            ),
            generationMetadata=(
                GenerationMetadataDto.model_validate(
                    generation_metadata.model_dump(mode="json", by_alias=True)
                )
                if generation_metadata
                else None
            ),
            personalizationSources=personalization_sources(learner, draft),
            status=package_status,
            targetSkill=draft.goalText,
            observableResponse=draft.observableResponse or draft.goalText,
            baseline=draft.baseline,
            objective=draft.goalText,
            successCriterion=f"Teacher confirms success across {draft.opportunities} planned opportunities.",
            responseModality=draft.responseLevel,
            preparationChecklist=[
                "Review learner communication access and accepted responses",
                "Prepare selected materials and a brief break option",
                "Confirm prompting and reinforcement choices",
                "Prepare the aligned data sheet",
            ],
            promptingPlan=PromptingPlanDto(
                startingPrompt=draft.promptingStart,
                permittedHierarchy=[
                    "Natural cue",
                    "Wait time",
                    "Visual or gestural prompt",
                    "Model prompt",
                    "Teacher-selected additional support",
                ],
                waitTime="5 seconds unless the teacher adapts it",
                fadingIntention="Reduce support as independent responding becomes stable",
                reduceSupportCriteria="Reduce one level after teacher-observed successful responding without distress",
                teacherOverride=draft.promptingLimits,
            ),
            reinforcementPlan=ReinforcementPlanDto(
                selectedSupport=draft.reinforcementPlan,
                deliveryTiming="Immediately after the confirmed target response or meaningful approximation",
                targetResponse=draft.observableResponse or draft.goalText,
                learnerChoice="Offer a choice when more than one confirmed support is available",
                alternativeWhenIneffective="Pause and offer another confirmed engagement support without withholding basic needs",
            ),
            errorCorrectionPlan=ErrorCorrectionPlanDto(
                neutralResponse="Use a neutral acknowledgement and preserve communication access",
                repeatOpportunity="Model or clarify, then offer another opportunity",
                supportAfterRepeatedError="Reduce difficulty, offer a break, or stop for team review",
                dataRecording="Record the outcome and prompt level without labeling the learner",
            ),
            generalizationPlan=GeneralizationPlanDto(
                examples=draft.scenarios or ["A familiar classroom example"],
                people=["Teacher", "Another familiar adult after initial success"],
                settings=[
                    "Teaching area",
                    "Another familiar setting after initial success",
                ],
                wording=[
                    draft.responseLevel,
                    "A teacher-confirmed equivalent response",
                ],
                materials=draft.selectedMaterials,
                responseFormats=[
                    draft.responseLevel,
                    "Established AAC, gesture, or picture response when applicable",
                ],
            ),
            dataSheetSpecification=DataSheetSpecificationDto(
                columns=[
                    "opportunity",
                    "independent",
                    "prompted",
                    "incorrect",
                    "no_response",
                    "prompt_level",
                    "latency",
                    "notes",
                ],
                summaryCalculation="Summarize independent and prompted responses separately; also note participation, regulation, and generalization attempts.",
            ),
            teacherAdaptation=TeacherAdaptationPlanDto(
                signsToPause=[
                    "Distress",
                    "Withdrawal",
                    "Repeated refusal",
                    "Loss of regulation",
                ],
                tooDifficultSigns=[
                    "Repeated errors despite support",
                    "Prompt level increases",
                    "Participation drops",
                ],
                tooEasySigns=[
                    "Consistent rapid independent responses",
                    "No meaningful variation required",
                ],
                howToShorten="Reduce opportunities, use one familiar context, and preserve closure.",
                howToIncreaseChallenge="Change one dimension at a time after stable success.",
                requiresTeamReview=[
                    "Safety concerns",
                    "New restrictive support request",
                    "Communication access changes",
                    "Persistent distress",
                ],
            ),
        )
        with self.repos.transaction():
            package = self.repos.lesson_packages.save(package)
            for material in materials:
                self.repos.generated_materials.save(material)
        return package

    def get_product(self, package_id: str) -> LessonPackageDto:
        package = self.repos.lesson_packages.get(package_id)
        if not package or not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        return package

    def update_product(
        self, package_id: str, payload: LessonPackageUpdateRequest
    ) -> LessonPackageDto:
        package = self.get_product(package_id)
        updates = {}
        if payload.lessonBrief is not None:
            updates["lessonBrief"] = payload.lessonBrief
        if payload.summaryTemplate is not None:
            updates["summaryTemplate"] = payload.summaryTemplate
        if payload.teachingFlow is not None:
            updates["teachingFlow"] = payload.teachingFlow
        if payload.documentContent is not None:
            updates["documentContent"] = payload.documentContent
        if payload.expectedVersion is not None:
            updates["version"] = payload.expectedVersion
        if package.status == "approved" and updates:
            updates["status"] = "teacher_review_needed"
        updated = self._reevaluate_product(package.model_copy(update=updates))
        return self.repos.lesson_packages.save(updated)

    def approve_product(
        self, package_id: str, payload: LessonPackageDecisionRequest
    ) -> LessonPackageDto:
        package = self.get_product(package_id)
        if package.version != payload.expectedVersion:
            from app.core.exceptions import VersionConflictError

            raise VersionConflictError(
                "The lesson package changed after it was loaded. Refresh and try again."
            )
        if package.safetyReview and package.safetyReview.status == "blocked":
            raise ConflictError("A safety-blocked lesson package cannot be approved")
        if any(check.status == "blocked" for check in package.standardsChecks):
            raise ConflictError(
                "Resolve blocked instructional quality checks before approval"
            )
        return self.repos.lesson_packages.save(
            package.model_copy(update={"status": "approved"})
        )

    def reject_product(
        self, package_id: str, payload: LessonPackageDecisionRequest
    ) -> LessonPackageDto:
        package = self.get_product(package_id)
        if package.version != payload.expectedVersion:
            from app.core.exceptions import VersionConflictError

            raise VersionConflictError(
                "The lesson package changed after it was loaded. Refresh and try again."
            )
        return self.repos.lesson_packages.save(
            package.model_copy(update={"status": "rejected"})
        )

    def regenerate_section(
        self,
        package_id: str,
        payload: LessonPackageRegenerateSectionRequest,
    ) -> LessonPackageDto:
        package = self.get_product(package_id)
        if package.version != payload.expectedVersion:
            from app.core.exceptions import VersionConflictError

            raise VersionConflictError(
                "The lesson package changed after it was loaded. Refresh and try again."
            )
        note = payload.teacherInstructions.strip() or "teacher-requested adaptation"
        updates: dict[str, object] = {"status": "teacher_review_needed"}
        if payload.section == "lessonBrief":
            updates["lessonBrief"] = f"{package.lessonBrief} Revision focus: {note}."
        elif payload.section == "summaryTemplate":
            updates["summaryTemplate"] = (
                f"{package.summaryTemplate}\nTeacher revision focus: {note}."
            )
        elif payload.section == "teachingFlow":
            updates["teachingFlow"] = [
                step.model_copy(
                    update={"description": f"{step.description} Adaptation: {note}."}
                )
                for step in package.teachingFlow
            ]
        elif payload.section == "promptingPlan" and package.promptingPlan:
            updates[payload.section] = package.promptingPlan.model_copy(
                update={
                    "teacherOverride": f"{package.promptingPlan.teacherOverride}; {note}"
                }
            )
        elif payload.section == "reinforcementPlan" and package.reinforcementPlan:
            updates[payload.section] = package.reinforcementPlan.model_copy(
                update={"alternativeWhenIneffective": note}
            )
        elif payload.section == "errorCorrectionPlan" and package.errorCorrectionPlan:
            updates[payload.section] = package.errorCorrectionPlan.model_copy(
                update={"supportAfterRepeatedError": note}
            )
        elif payload.section == "generalizationPlan" and package.generalizationPlan:
            updates[payload.section] = package.generalizationPlan.model_copy(
                update={"examples": [*package.generalizationPlan.examples, note]}
            )
        elif (
            payload.section == "dataSheetSpecification"
            and package.dataSheetSpecification
        ):
            updates[payload.section] = package.dataSheetSpecification.model_copy(
                update={"summaryCalculation": note}
            )
        elif payload.section == "teacherAdaptation" and package.teacherAdaptation:
            updates[payload.section] = package.teacherAdaptation.model_copy(
                update={"howToShorten": note}
            )
        else:
            raise ValidationError("The requested section is not available")
        regenerated = self._reevaluate_product(package.model_copy(update=updates))
        return self.repos.lesson_packages.save(regenerated)

    def list_product_versions(self, package_id: str) -> list[LessonPackageVersionDto]:
        self.get_product(package_id)
        return [
            LessonPackageVersionDto(
                packageId=package_id,
                version=item.version,
                status=item.status,
                snapshot=item,
            )
            for item in self.repos.lesson_packages.list_versions(package_id)
            if isinstance(item, LessonPackageDto)
        ]

    def list_products(self, learner_id: str | None = None) -> list[LessonPackageDto]:
        packages = [
            item
            for item in self.repos.lesson_packages.list()
            if isinstance(item, LessonPackageDto)
        ]
        if learner_id is not None:
            packages = [item for item in packages if item.learnerId == learner_id]
        return sorted(packages, key=lambda item: item.id, reverse=True)

    def compare_product_versions(
        self, package_id: str, from_version: int, to_version: int
    ) -> LessonPackageVersionComparisonDto:
        before = self.repos.lesson_packages.get_version(package_id, from_version)
        after = self.repos.lesson_packages.get_version(package_id, to_version)
        if not isinstance(before, LessonPackageDto) or not isinstance(
            after, LessonPackageDto
        ):
            raise NotFoundError("Lesson package version not found")
        before_data = before.model_dump(mode="json", by_alias=True)
        after_data = after.model_dump(mode="json", by_alias=True)
        changed = sorted(
            key
            for key in set(before_data) | set(after_data)
            if key != "version" and before_data.get(key) != after_data.get(key)
        )
        return LessonPackageVersionComparisonDto(
            packageId=package_id,
            fromVersion=from_version,
            toVersion=to_version,
            changedFields=changed,
            fromSnapshot=before,
            toSnapshot=after,
        )

    def restore_product_version(
        self, package_id: str, version: int, expected_version: int
    ) -> LessonPackageDto:
        current = self.get_product(package_id)
        if current.version != expected_version:
            from app.core.exceptions import VersionConflictError

            raise VersionConflictError(
                "The lesson package changed after it was loaded. Refresh and try again."
            )
        snapshot = self.repos.lesson_packages.get_version(package_id, version)
        if not isinstance(snapshot, LessonPackageDto):
            raise NotFoundError("Lesson package version not found")
        restored = snapshot.model_copy(
            update={
                "version": current.version,
                "status": "teacher_review_needed",
            },
            deep=True,
        )
        return self.repos.lesson_packages.save(restored)

    def get_product_materials(self, package_id: str) -> list[GeneratedMaterialDto]:
        return self.get_product(package_id).materials

    def _reevaluate_product(self, package: LessonPackageDto) -> LessonPackageDto:
        """Never carry stale safety or quality decisions across teacher edits."""

        prompting = package.promptingPlan
        reinforcement = package.reinforcementPlan
        error = package.errorCorrectionPlan
        generalization = package.generalizationPlan
        draft = LessonDesignDraftDto(
            id=package.draftId,
            learnerId=package.learnerId,
            goalText=package.goal,
            observableResponse=package.observableResponse or package.goal,
            baseline=package.baseline,
            responseLevel=package.responseModality,
            scenarios=generalization.examples if generalization else [],
            selectedMaterials=[item.title for item in package.materials],
            theme=package.theme,
            duration=package.duration,
            customNotes="",
            promptingStart=prompting.startingPrompt if prompting else "",
            promptingLimits=prompting.teacherOverride if prompting else "",
            reinforcementPlan=(reinforcement.selectedSupport if reinforcement else ""),
            errorCorrection=error.neutralResponse if error else "",
            dataCollection="Record response outcome and prompt level",
            generalizationPlan=(
                "Vary examples, people, settings, wording, materials, and response formats"
                if generalization
                else ""
            ),
        )
        content = {
            "lessonBrief": package.lessonBrief,
            "summaryTemplate": package.summaryTemplate,
            "teachingFlow": [
                item.model_dump(mode="json", by_alias=True)
                for item in package.teachingFlow
            ],
            "documentContent": package.documentContent,
        }
        safety_review = self.safety.review_product(draft, content)
        checks = self.standards.evaluate_product(draft, package.materials, content)
        status = (
            "safety_review_needed"
            if safety_review.status == "blocked"
            else (
                "validation_failed"
                if any(item.status == "blocked" for item in checks)
                else "teacher_review_needed"
            )
        )
        return package.model_copy(
            update={
                "safetyReview": safety_review,
                "standardsChecks": checks,
                "status": status,
            }
        )

    @staticmethod
    def _parse_product_flow(
        generated: object, fallback: list[dict]
    ) -> list[TeachingStepDto]:
        source = generated if isinstance(generated, list) and generated else fallback
        try:
            flow = [TeachingStepDto.model_validate(item) for item in source]
            return (
                flow
                if flow
                else [TeachingStepDto.model_validate(item) for item in fallback]
            )
        except Exception:
            return [TeachingStepDto.model_validate(item) for item in fallback]

    @staticmethod
    def _enrich_product_flow(
        flow: list[TeachingStepDto], draft: LessonDesignDraftDto
    ) -> list[TeachingStepDto]:
        """Fill the complete teacher-action contract without changing provider prose."""

        phases = ("prepare", "model", "guided_practice", "independent", "close")
        enriched: list[TeachingStepDto] = []
        for index, step in enumerate(flow):
            phase = phases[min(index, len(phases) - 1)]
            independent = phase == "independent"
            enriched.append(
                step.model_copy(
                    update={
                        "phase": phase,
                        "teacherScript": step.teacherScript
                        or (
                            None
                            if phase == "prepare"
                            else f"Show or say: {draft.observableResponse or draft.goalText}"
                        ),
                        "expectedLearnerResponse": step.expectedLearnerResponse
                        or draft.observableResponse
                        or draft.goalText,
                        "waitTime": step.waitTime
                        or "5 seconds, adapted by the teacher",
                        "promptAction": step.promptAction
                        or (
                            "Use the confirmed starting prompt, then fade when appropriate"
                            if not independent
                            else "Wait before using the least support needed"
                        ),
                        "reinforcementAction": step.reinforcementAction
                        or "Acknowledge the target response and offer the confirmed engagement support",
                        "errorCorrectionAction": step.errorCorrectionAction
                        or "Respond neutrally, model or clarify, and offer another opportunity",
                        "dataToRecord": step.dataToRecord
                        or [
                            "independent",
                            "prompted",
                            "incorrect",
                            "no response",
                            "prompt level",
                            "brief teacher note",
                        ],
                        "transitionCue": step.transitionCue
                        or "Preview the next short step with a visual or brief statement",
                        "breakOption": step.breakOption
                        or "Pause or offer the learner's established break response when needed",
                    }
                )
            )
        return enriched

    @staticmethod
    def _is_valid_product_flow(generated: object) -> bool:
        if not isinstance(generated, list) or not generated:
            return False
        try:
            return bool([TeachingStepDto.model_validate(item) for item in generated])
        except Exception:
            return False

    def _generated_materials_cover_draft(
        self, generated: object, draft: LessonDesignDraftDto
    ) -> bool:
        if not isinstance(generated, list):
            return False
        provided = {
            str(item.get("type"))
            for item in generated
            if isinstance(item, dict) and isinstance(item.get("content"), dict)
        }
        required = {
            material_type
            for material_type in (
                self._material_type_for_selection(item)
                for item in draft.selectedMaterials
            )
            if material_type
        }
        return required.issubset(provided)

    @staticmethod
    def _material_type_for_selection(value: str) -> str | None:
        normalized = " ".join(value.replace("_", " ").casefold().split())
        return {
            "visual cards": "visual_card",
            "visual card": "visual_card",
            "choice board": "choice_board",
            "choice boards": "choice_board",
            "first then board": "first_then_board",
            "first-then board": "first_then_board",
            "help cards": "help_card",
            "help card": "help_card",
            "break card": "break_card",
            "token boards": "token_board",
            "token board": "token_board",
            "sorting page": "sorting_page",
            "matching page": "matching_page",
            "scenario cards": "scenario_cards",
            "teacher cue card": "teacher_cue_card",
            "data sheets": "data_sheet",
            "data sheet": "data_sheet",
            "session summary": "session_summary",
            "summary templates": "summary_template",
            "summary template": "summary_template",
            "handoff note": "handoff_note",
        }.get(normalized)

    def _build_product_materials(
        self,
        package_id: str,
        draft: LessonDesignDraftDto,
        generated: object,
        fallback: list[dict],
    ) -> list[GeneratedMaterialDto]:
        selected_types = [
            material_type
            for material_type in (
                self._material_type_for_selection(item)
                for item in draft.selectedMaterials
            )
            if material_type
        ]
        if "ask for help" in draft.goalText.casefold():
            selected_types.append("help_card")
        selected_types.append("summary_template")
        selected_types = list(dict.fromkeys(selected_types))
        canonical_order = {
            "visual_card": 0,
            "choice_board": 1,
            "first_then_board": 2,
            "help_card": 3,
            "break_card": 4,
            "token_board": 5,
            "sorting_page": 6,
            "matching_page": 7,
            "scenario_cards": 8,
            "teacher_cue_card": 9,
            "data_sheet": 10,
            "session_summary": 11,
            "summary_template": 12,
            "handoff_note": 13,
        }
        selected_types.sort(key=lambda item: canonical_order[item])
        definitions = generated if isinstance(generated, list) else []
        fallback_by_type = {item["type"]: item for item in fallback}
        generated_by_type = {
            str(item.get("type")): item
            for item in definitions
            if isinstance(item, dict) and isinstance(item.get("content"), dict)
        }
        materials: list[GeneratedMaterialDto] = []
        for material_type in selected_types:
            definition = (
                generated_by_type.get(material_type)
                or fallback_by_type.get(material_type)
                or self._default_material_definition(material_type, draft)
            )
            content = dict(definition.get("content") or {})
            for key in ("imageConcept", "imagePrompt", "imageAltText"):
                if isinstance(definition.get(key), str):
                    content[key] = definition[key]
            materials.append(
                GeneratedMaterialDto(
                    id=self.repos.next_id("material"),
                    packageId=package_id,
                    type=material_type,
                    title=str(
                        definition.get("title")
                        or material_type.replace("_", " ").title()
                    ),
                    status="teacher_review_needed",
                    content=content,
                    printLayout={
                        "pageSize": "Letter",
                        "orientation": (
                            "landscape"
                            if material_type == "token_board"
                            else "portrait"
                        ),
                        "color": "blue",
                    },
                    specification=self._build_material_specification(
                        material_type, content, draft
                    ),
                )
            )
        return materials

    @staticmethod
    def _default_material_definition(
        material_type: str, draft: LessonDesignDraftDto
    ) -> dict:
        return {
            "type": material_type,
            "title": material_type.replace("_", " ").title(),
            "content": {
                "instruction": draft.observableResponse or draft.goalText,
                "examples": draft.scenarios,
            },
        }

    @staticmethod
    def _build_material_specification(
        material_type: str, content: dict, draft: LessonDesignDraftDto
    ):
        common = {
            "purpose": f"Support the teacher-confirmed target: {draft.goalText}",
            "audience": "learner",
            "pageSize": "Letter",
            "orientation": (
                "landscape" if material_type == "token_board" else "portrait"
            ),
            "margins": "0.5 in print-safe margins",
            "textLimit": "One short direction and brief labels",
            "imageNeed": (
                "required"
                if material_type in {"visual_card", "choice_board", "scenario_cards"}
                else "optional"
            ),
            "contrastGuidance": "High contrast; do not rely on color alone",
            "printPreparation": [
                "Review wording",
                "Check margins",
                "Print at actual size",
            ],
            "editableFields": ["title", "instruction", "examples"],
            "altText": str(
                content.get("imageAltText") or "Teacher-reviewed instructional support"
            ),
        }
        response = draft.responseLevel or draft.observableResponse or draft.goalText
        if material_type == "visual_card":
            return VisualCardSpecification(
                **common,
                label=response,
                visualConcept=str(
                    content.get("imageConcept")
                    or (draft.scenarios[0] if draft.scenarios else "classroom response")
                ),
            )
        if material_type == "choice_board":
            return ChoiceBoardSpecification(
                **common, options=draft.scenarios[:4] or ["Choice 1", "Choice 2"]
            )
        if material_type == "first_then_board":
            return FirstThenBoardSpecification(
                **common, firstText="Practice", thenText="Teacher-confirmed choice"
            )
        if material_type == "help_card":
            return HelpCardSpecification(**common, requestText=response)
        if material_type == "break_card":
            return BreakCardSpecification(
                **common,
                requestText="Break, please",
                returnCue="Return when ready with teacher support",
            )
        if material_type == "token_board":
            return TokenBoardSpecification(
                **common, tokenCount=5, rewardLabel="Teacher-confirmed choice"
            )
        if material_type == "sorting_page":
            return SortingPageSpecification(
                **common, categories=["Group 1", "Group 2"], items=draft.scenarios
            )
        if material_type == "matching_page":
            pairs = [(item, item) for item in (draft.scenarios[:4] or ["Example"])]
            return MatchingPageSpecification(**common, pairs=pairs)
        if material_type == "scenario_cards":
            return ScenarioCardsSpecification(**common, scenarios=draft.scenarios)
        if material_type == "teacher_cue_card":
            return TeacherCueCardSpecification(
                **{**common, "audience": "teacher", "imageNeed": "none"},
                cueSteps=[
                    "Present opportunity",
                    draft.promptingStart,
                    draft.errorCorrection,
                    "Record data",
                ],
            )
        if material_type == "data_sheet":
            return DataSheetMaterialSpecification(
                **{**common, "audience": "teacher", "imageNeed": "none"},
                columns=[
                    "Opportunity",
                    "Independent",
                    "Prompted",
                    "Incorrect",
                    "No response",
                    "Prompt level",
                    "Latency",
                    "Notes",
                ],
                summaryCalculation="Summarize independent and prompted outcomes separately.",
            )
        if material_type in {"session_summary", "summary_template"}:
            return SessionSummarySpecification(
                **{
                    **common,
                    "type": material_type,
                    "audience": "teacher",
                    "imageNeed": "none",
                },
                prompts=[
                    "What worked?",
                    "What support was used?",
                    "Small wins",
                    "Next step",
                ],
            )
        return HandoffNoteSpecification(
            **{**common, "audience": "teacher", "imageNeed": "none"},
            fields=["Goal", "Support used", "Learner response", "Next step"],
        )

    @staticmethod
    def _fallback_product_content(
        draft: LessonDesignDraftDto, learner_context: dict
    ) -> dict:
        from app.integrations.mock_ai_provider import MockV2AIProvider

        selected = list(draft.selectedMaterials)
        if "ask for help" in draft.goalText.casefold() and "Help Card" not in selected:
            selected.append("Help Card")
        if "Summary Template" not in selected:
            selected.append("Summary Template")
        fallback_draft = draft.model_copy(update={"selectedMaterials": selected})
        return MockV2AIProvider().generate_lesson_package(
            fallback_draft, learner_context
        )

    def _prepare_product_material_images(
        self, learner, materials: list[GeneratedMaterialDto]
    ) -> None:
        for material in materials:
            if material.type not in {"visual_card", "help_card", "token_board"}:
                continue
            concept = str(material.content.get("imageConcept") or "").strip()
            if not concept:
                continue
            prompt, alt_text = build_safe_image_prompt(
                learner,
                material.type,
                concept,
                str(material.content.get("imagePrompt") or ""),
            )
            safe_concept = build_image_generation_context(
                learner, material.type, concept
            )["concept"]
            asset = self.images.prepare_generated_image_for_material(
                learner_id=learner.id,
                material_id=material.id,
                material_type=material.type,
                concept=safe_concept,
                prompt=prompt,
                style="clean printable educational illustration",
                size="1024x1024",
            )
            content = dict(material.content)
            content.update(
                {
                    "imageConcept": asset.concept,
                    "imagePrompt": prompt,
                    "imageAssetId": asset.id,
                    "imageUrl": asset.imageUrl or asset.thumbnailUrl,
                    "imageBase64": None if asset.imageUrl else asset.imageBase64,
                    "imageAltText": alt_text,
                    "imageSourceType": asset.sourceType,
                    "imageLicenseInfo": asset.licenseInfo,
                    "imageSafetyStatus": asset.safetyStatus,
                }
            )
            material.content = content

    @staticmethod
    def _build_flow() -> list[TeachingStep]:
        return [
            TeachingStep(
                id="warm-up",
                title="Warm-up",
                description="Preview the goal and visuals.",
                duration="2 min",
                teacher_action="Model the target response.",
                learner_action="Attend and respond when ready.",
            ),
            TeachingStep(
                id="practice",
                title="Guided practice",
                description="Practice in selected scenarios.",
                duration="6 min",
                teacher_action="Create opportunities and fade prompts.",
                learner_action="Practice the target skill.",
            ),
            TeachingStep(
                id="generalize",
                title="Generalize",
                description="Use the skill in a new context.",
                duration="2 min",
                teacher_action="Offer a natural opportunity.",
                learner_action="Try the skill with less support.",
            ),
        ]

    def _build_materials(
        self, package_id: str, selected: list[str]
    ) -> list[GeneratedMaterial]:
        definitions = {
            "Visual Cards": (
                "visual_card",
                "Visual Card",
                {"instruction": "I need help", "artwork": "Communication prompt"},
            ),
            "Token Board": (
                "token_board",
                "Token Board",
                {
                    "instruction": "Earn 5 stars, then get a reward!",
                    "reward": "Car",
                    "tokens": 5,
                },
            ),
            "Data Sheet": (
                "data_sheet",
                "Data Sheet",
                {"columns": ["Scenario", "Independent", "Prompted", "Notes"]},
            ),
            "Summary Template": (
                "summary_template",
                "Summary Template",
                {"instruction": "Record what worked and next steps."},
            ),
        }
        names = list(dict.fromkeys([*selected, "Summary Template"]))
        result: list[GeneratedMaterial] = []
        for name in names:
            material_type, title, content = definitions.get(
                name, ("help_card", name, {"instruction": name})
            )
            result.append(
                GeneratedMaterial(
                    id=self.repos.next_id("material"),
                    package_id=package_id,
                    type=material_type,
                    title=title,
                    content=content,
                    print_layout=PrintLayout(
                        orientation=(
                            "landscape"
                            if material_type == "token_board"
                            else "portrait"
                        )
                    ),
                )
            )
        return result
