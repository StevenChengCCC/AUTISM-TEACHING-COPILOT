from __future__ import annotations

import logging

from app.core.config import Settings, settings
from app.core.exceptions import (
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
    EmotionScaleSpecification,
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
    LessonSectionEditPreviewDto,
    LessonSectionEditPreviewRequest,
    LessonPackageUpdateRequest,
    LessonPackageVersionComparisonDto,
    LessonPackageVersionDto,
    QuantityCardsSpecification,
    PromptingPlanDto,
    PrintLayout,
    ReinforcementPlanDto,
    CoreWordBoardSpecification,
    SessionSummarySpecification,
    ScenarioCardsSpecification,
    SequenceCardsSpecification,
    SocialNarrativeSpecification,
    SortingPageSpecification,
    MatchingPageSpecification,
    NumberCardsSpecification,
    TeachingStep,
    TeachingStepDto,
    TeacherAdaptationPlanDto,
    TeacherCueCardSpecification,
    TaskAnalysisCardsSpecification,
    TokenBoardSpecification,
    VisualCardSpecification,
    VisualScheduleSpecification,
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
from app.services.v2_material_service import V2MaterialService
from app.services.v2_material_blueprint_service import V2MaterialBlueprintService
from app.services.v2_lesson_package_quality_service import (
    V2LessonPackageQualityService,
)
from app.services.v2_safety_harness_service import V2SafetyHarnessService
from app.services.v2_standards_skill_service import V2StandardsSkillService


logger = logging.getLogger(__name__)


class V2LessonPackageService:
    image_material_types = {
        "quantity_cards",
        "number_cards",
        "visual_card",
        "scenario_cards",
        "sequence_cards",
        "social_narrative",
        "core_word_board",
        "visual_schedule",
        "task_analysis_cards",
        "emotion_scale",
        "sorting_page",
        "matching_page",
        "choice_board",
        "first_then_board",
        "help_card",
        "break_card",
        "teacher_cue_card",
        "token_board",
    }

    def __init__(
        self,
        repos: V2Repositories = repositories,
        ai: V2AIProvider | None = None,
        safety: V2SafetyHarnessService | None = None,
        standards: V2StandardsSkillService | None = None,
        quality: V2LessonPackageQualityService | None = None,
        images: V2ImageAssetService | None = None,
        config: Settings = settings,
    ):
        self.repos = repos
        self.ai = ai or get_v2_ai_provider()
        self.safety = safety or V2SafetyHarnessService()
        self.standards = standards or V2StandardsSkillService()
        self.quality = quality or V2LessonPackageQualityService()
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
        if invalid_provider_output:
            logger.warning(
                "lesson_package_structural_defaults_applied",
                extra={
                    "event": "lesson_package_structural_defaults_applied",
                    "provider": provider_name,
                },
            )
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
        quality_score = self.quality.evaluate(draft, package)
        if quality_score.overallStatus == "blocked":
            package = package.model_copy(
                update={
                    "qualityScore": quality_score,
                    "status": (
                        package.status
                        if package.status == "safety_review_needed"
                        else "validation_failed"
                    ),
                }
            )
        else:
            package = package.model_copy(update={"qualityScore": quality_score})
        with self.repos.transaction():
            package = self.repos.lesson_packages.save(package)
            for material in materials:
                self.repos.generated_materials.save(material)
        return package

    def queue_product_images(self, package_id: str) -> LessonPackageDto:
        """Mark every planned classroom visual pending without provider calls."""

        package = self.get_product(package_id)
        material_service = V2MaterialService(self.repos)
        for material in package.materials:
            if material.type not in self.image_material_types:
                continue
            visual_items = material.content.get("visualItems")
            if not isinstance(visual_items, list) or not visual_items:
                continue
            pending_items = [
                {
                    **item,
                    "generationStatus": "pending",
                }
                for item in visual_items
                if isinstance(item, dict)
            ]
            material_service.attach_visual_assets(
                material.id,
                pending_items,
                overall_status="pending",
            )
        return self.get_product(package_id)

    def prepare_product_images(self, package_id: str) -> None:
        """Generate package images after the package response has been returned."""

        package = self.get_product(package_id)
        for material in package.materials:
            if material.type not in self.image_material_types:
                continue
            if not material.content.get("visualItems"):
                continue
            try:
                self.prepare_material_image(material.id)
            except Exception:
                logger.warning(
                    "material_image_generation_failed",
                    extra={
                        "event": "material_image_generation_failed",
                        "material_id": material.id,
                    },
                )
                try:
                    V2MaterialService(self.repos).set_image_generation_status(
                        material.id,
                        "failed",
                        "Artwork could not be generated. The lesson material is still available.",
                    )
                except Exception:
                    logger.warning(
                        "material_image_failure_status_not_saved",
                        extra={
                            "event": "material_image_failure_status_not_saved",
                            "material_id": material.id,
                        },
                    )

    def prepare_material_image(
        self, material_id: str, *, force_generation: bool = False
    ) -> GeneratedMaterialDto:
        material = self.repos.generated_materials.get(material_id)
        if not material or not isinstance(material, GeneratedMaterialDto):
            raise NotFoundError("Generated material not found")
        if material.type not in self.image_material_types:
            raise ValidationError("This material does not require generated artwork")
        package = self.get_product(material.packageId)
        learner = self.learners.get(package.learnerId)
        planned_items = material.content.get("visualItems")
        if not isinstance(planned_items, list) or not planned_items:
            raise ValidationError("This material does not have a visual asset plan")

        material_service = V2MaterialService(self.repos)
        material_service.set_image_generation_status(material.id, "processing")
        interest = next(
            (str(item).strip() for item in learner.interests if str(item).strip()),
            package.theme or "classroom",
        )
        assets_by_concept: dict[str, object] = {}
        completed_items: list[dict] = []
        for raw_item in planned_items:
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            concept = str(item.get("concept") or "").strip()
            if item.get("assetRole") == "countable_object":
                concept = f"one isolated {interest} themed counting object"
            if not concept:
                continue
            safe_concept = build_image_generation_context(
                learner, material.type, concept
            )["concept"]
            asset = assets_by_concept.get(safe_concept)
            if asset is None:
                prompt, _ = build_safe_image_prompt(
                    learner,
                    material.type,
                    safe_concept,
                    str(item.get("prompt") or material.content.get("imagePrompt") or ""),
                )
                asset = self.images.prepare_generated_image_for_material(
                    learner_id=learner.id,
                    material_id="",
                    material_type=material.type,
                    concept=safe_concept,
                    prompt=prompt,
                    style=(
                        "clean printable special-education material asset; "
                        "isolated subject; white background; no text"
                    ),
                    size="1024x1024",
                    force_generation=force_generation,
                )
                assets_by_concept[safe_concept] = asset
            item.update(
                {
                    "concept": safe_concept,
                    "imageAssetId": asset.id,
                    "imageUrl": asset.imageUrl or asset.thumbnailUrl,
                    "imageBase64": None if asset.imageUrl else asset.imageBase64,
                    "imageAltText": asset.altText,
                    "imageSourceType": asset.sourceType,
                    "imageLicenseInfo": asset.licenseInfo,
                    "imageSafetyStatus": asset.safetyStatus,
                    "generationStatus": (
                        "ready"
                        if asset.sourceType in {"generated", "internal"}
                        else (
                            "needs_review"
                            if asset.sourceType
                            in {"pexels", "pixabay", "unsplash"}
                            else "failed"
                        )
                    ),
                }
            )
            completed_items.append(item)
        if not completed_items:
            raise ValidationError("No classroom visual assets could be prepared")
        item_statuses = {
            str(item.get("generationStatus") or "") for item in completed_items
        }
        overall_status = (
            "failed"
            if "failed" in item_statuses
            else "needs_review"
            if "needs_review" in item_statuses
            else "ready"
        )
        material_service.attach_visual_assets(
            material.id,
            completed_items,
            overall_status=overall_status,
        )
        updated = self.repos.generated_materials.get(material.id)
        if not updated or not isinstance(updated, GeneratedMaterialDto):
            raise NotFoundError("Generated material not found")
        return updated

    def get_product(self, package_id: str) -> LessonPackageDto:
        package = self.repos.lesson_packages.get(package_id)
        if not package or not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        current_score = self.quality.evaluate(
            self._draft_for_product_quality(package),
            package,
        )
        if current_score != package.qualityScore:
            return package.model_copy(update={"qualityScore": current_score})
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
        if package.qualityScore and package.qualityScore.overallStatus == "blocked":
            raise ConflictError(
                "Resolve blocked lesson package quality items before approval"
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

    def preview_section_edit(
        self,
        package_id: str,
        payload: LessonSectionEditPreviewRequest,
    ) -> LessonSectionEditPreviewDto:
        package = self.get_product(package_id)
        if package.version != payload.expectedVersion:
            from app.core.exceptions import VersionConflictError

            raise VersionConflictError(
                "The lesson package changed after it was loaded. Refresh and try again."
            )
        revised = self.ai.revise_lesson_section(
            section_label=payload.sectionLabel,
            current_text=payload.currentText,
            instruction=payload.instruction,
            lesson_context={
                "goal": package.goal,
                "theme": package.theme,
                "duration": package.duration,
                "learnerId": package.learnerId,
            },
        ).strip()
        if not revised:
            raise ValidationError("The AI revision was empty. Nothing was changed.")
        return LessonSectionEditPreviewDto(
            packageId=package.id,
            sectionId=payload.sectionId,
            sectionLabel=payload.sectionLabel,
            beforeText=payload.currentText,
            revisedText=revised,
            instruction=payload.instruction,
            providerUsed=self.ai.provider_name,
            fallbackUsed=bool(getattr(self.ai, "last_fallback_used", False)),
        )

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

        draft = self._draft_for_product_quality(package)
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
        reevaluated = package.model_copy(
            update={
                "safetyReview": safety_review,
                "standardsChecks": checks,
                "status": status,
            }
        )
        quality_score = self.quality.evaluate(draft, reevaluated)
        if (
            quality_score.overallStatus == "blocked"
            and status != "safety_review_needed"
        ):
            status = "validation_failed"
        return reevaluated.model_copy(
            update={
                "qualityScore": quality_score,
                "status": status,
            }
        )

    @staticmethod
    def _draft_for_product_quality(
        package: LessonPackageDto,
    ) -> LessonDesignDraftDto:
        prompting = package.promptingPlan
        reinforcement = package.reinforcementPlan
        error = package.errorCorrectionPlan
        generalization = package.generalizationPlan
        return LessonDesignDraftDto(
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
        normalized = " ".join(
            value.replace("_", " ")
            .replace("–", "-")
            .replace("—", "-")
            .casefold()
            .split()
        )
        exact = {
            "quantity cards": "quantity_cards",
            "quantity card": "quantity_cards",
            "number cards": "number_cards",
            "number card": "number_cards",
            "visual number cards": "number_cards",
            "counting cards": "quantity_cards",
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
            "reinforcement board": "token_board",
            "sorting page": "sorting_page",
            "matching page": "matching_page",
            "matching practice": "matching_page",
            "scenario cards": "scenario_cards",
            "sequence cards": "sequence_cards",
            "sequencing cards": "sequence_cards",
            "social narrative": "social_narrative",
            "social situation guide": "social_narrative",
            "core word board": "core_word_board",
            "communication board": "core_word_board",
            "visual schedule": "visual_schedule",
            "task analysis cards": "task_analysis_cards",
            "task analysis": "task_analysis_cards",
            "emotion scale": "emotion_scale",
            "regulation scale": "emotion_scale",
            "teacher cue card": "teacher_cue_card",
            "data sheets": "data_sheet",
            "data sheet": "data_sheet",
            "session summary": "session_summary",
            "summary templates": "summary_template",
            "summary template": "summary_template",
            "lesson summary": "summary_template",
            "handoff note": "handoff_note",
        }.get(normalized)
        if exact:
            return exact
        if "number" in normalized and "card" in normalized:
            return "number_cards"
        if "quantity" in normalized and "card" in normalized:
            return "quantity_cards"
        if "first then" in normalized or "first-then" in normalized:
            return "first_then_board"
        if (
            "token" in normalized
            or "reward" in normalized
            or "reinforcement board" in normalized
        ):
            return "token_board"
        if "choice" in normalized:
            return "choice_board"
        if "help" in normalized:
            return "help_card"
        if "break" in normalized:
            return "break_card"
        if "sort" in normalized:
            return "sorting_page"
        if "match" in normalized:
            return "matching_page"
        if "scenario" in normalized:
            return "scenario_cards"
        if "sequence" in normalized:
            return "sequence_cards"
        if "social narrative" in normalized or "social situation" in normalized:
            return "social_narrative"
        if "core word" in normalized or "communication board" in normalized:
            return "core_word_board"
        if "schedule" in normalized:
            return "visual_schedule"
        if "task analysis" in normalized or "step card" in normalized:
            return "task_analysis_cards"
        if "emotion scale" in normalized or "regulation scale" in normalized:
            return "emotion_scale"
        if "data" in normalized or "tracking" in normalized:
            return "data_sheet"
        if "summary" in normalized:
            return "summary_template"
        if "teacher" in normalized and ("cue" in normalized or "prompt" in normalized):
            return "teacher_cue_card"
        if "card" in normalized or "picture" in normalized or "visual" in normalized:
            return "visual_card"
        return None

    def _build_product_materials(
        self,
        package_id: str,
        draft: LessonDesignDraftDto,
        generated: object,
        fallback: list[dict],
    ) -> list[GeneratedMaterialDto]:
        teacher_selected_types = [
            material_type
            for material_type in (
                self._material_type_for_selection(item)
                for item in draft.selectedMaterials
            )
            if material_type
        ]
        # The material question is a teacher decision, not a decorative filter.
        # Generate exactly the confirmed pages; the later print review controls
        # which of those generated pages are included in a combined PDF.
        selected_types = list(dict.fromkeys(teacher_selected_types))
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
            content = self._ensure_visual_content(material_type, content, draft)
            content.setdefault(
                "designVariants",
                [
                    {
                        "id": "calm-blue",
                        "label": "Calm blue",
                        "color": "blue",
                        "description": "Clear, calm, and low-distraction.",
                        "background": "#f5f9ff",
                        "surface": "#ffffff",
                        "border": "#2563eb",
                        "accent": "#dbeafe",
                        "typography": "high-legibility",
                        "layout": "spacious-grid",
                        "artworkTreatment": "large isolated illustration",
                    },
                    {
                        "id": "playful-green",
                        "label": "Playful green",
                        "color": "green",
                        "description": "Friendly color with soft contrast.",
                        "background": "#f4fbf6",
                        "surface": "#ffffff",
                        "border": "#16a34a",
                        "accent": "#dcfce7",
                        "typography": "rounded-friendly",
                        "layout": "soft-card-grid",
                        "artworkTreatment": "framed themed illustration",
                    },
                    {
                        "id": "warm-gold",
                        "label": "Warm gold",
                        "color": "gold",
                        "description": "Warm, motivating classroom style.",
                        "background": "#fffaf0",
                        "surface": "#ffffff",
                        "border": "#d97706",
                        "accent": "#fef3c7",
                        "typography": "bold-classroom",
                        "layout": "banner-and-cards",
                        "artworkTreatment": "warm poster illustration",
                    },
                ],
            )
            content.setdefault("selectedDesignVariant", "calm-blue")
            materials.append(
                GeneratedMaterialDto(
                    id=self.repos.next_id("material"),
                    packageId=package_id,
                    type=material_type,
                    title=str(
                        definition.get("title")
                        or (
                            V2MaterialBlueprintService.blueprint(material_type).display_name
                            if V2MaterialBlueprintService.blueprint(material_type)
                            else material_type.replace("_", " ").title()
                        )
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
    def _recommended_material_types(
        draft: LessonDesignDraftDto,
    ) -> list[str]:
        """Resolve a minimum complete kit from the instructional goal family."""

        return V2MaterialBlueprintService.recommended_bundle(draft)

    @classmethod
    def _ensure_visual_content(
        cls,
        material_type: str,
        content: dict,
        draft: LessonDesignDraftDto,
    ) -> dict:
        """Guarantee that every visual classroom material requests real artwork.

        Provider-authored JSON is flexible, but a printable material needs an
        explicit asset plan.  A single decorative image cannot represent a choice
        board, a sequence, or a set of counting cards, so each meaningful visual
        unit receives its own item in ``visualItems``.
        """

        if material_type not in cls.image_material_types:
            return content

        updated = dict(content)
        theme = " ".join((draft.theme or "classroom").split())
        scenario = next(
            (
                " ".join(str(item).split())
                for item in draft.scenarios
                if str(item).strip()
            ),
            "",
        )
        context = scenario or theme
        if material_type in {
            "quantity_cards",
            "number_cards",
            "visual_card",
            "scenario_cards",
            "sequence_cards",
            "social_narrative",
            "core_word_board",
            "visual_schedule",
            "task_analysis_cards",
            "emotion_scale",
            "sorting_page",
            "matching_page",
        }:
            concept = f"{theme} learning visual for {context}"
        elif material_type in {"help_card", "break_card", "teacher_cue_card"}:
            concept = f"clear classroom communication symbol for {context}"
        elif material_type in {"choice_board", "first_then_board"}:
            concept = f"two clear classroom choices for {context}"
        else:
            concept = f"positive classroom reward symbol themed around {theme}"

        existing_concept = str(updated.get("imageConcept") or "").strip()
        existing_prompt = str(updated.get("imagePrompt") or "").strip()
        updated["imageConcept"] = existing_concept or concept
        updated["imagePrompt"] = existing_prompt or (
            f"Create one polished educational illustration for {concept}. "
            "Use an uncluttered white or very light background, bold friendly "
            "shapes, high contrast, and age-respectful classroom objects. "
            "Do not include words, letters, numerals, logos, watermarks, "
            "diagnostic labels, or an identifiable child."
        )
        updated["imageAltText"] = str(
            updated.get("imageAltText")
            or f"Teacher-reviewable illustration for {context}."
        )
        updated["visualItems"] = cls._build_visual_asset_plan(
            material_type, updated, draft
        )
        updated.setdefault("imageGenerationStatus", "not_started")
        return updated

    @classmethod
    def _build_visual_asset_plan(
        cls,
        material_type: str,
        content: dict,
        draft: LessonDesignDraftDto,
    ) -> list[dict]:
        """Describe the exact visual assets needed by a usable material.

        The image model creates artwork only.  Labels, quantities, cutting lines,
        and page geometry remain deterministic so the final material is accurate.
        """

        theme = " ".join((draft.theme or "classroom").split())
        labels = cls._material_labels(material_type, content, draft)
        base_prompt = (
            "Create one isolated, age-respectful educational illustration of "
            "{concept}. Use a plain white background, a single clear focal "
            "subject, bold friendly shapes, and high contrast. Do not include "
            "words, letters, numerals, logos, watermarks, borders, worksheets, "
            "or an identifiable child."
        )
        count_labels = cls._counting_labels(
            " ".join(
                str(value)
                for value in (
                    draft.goalText,
                    draft.observableResponse,
                    draft.theme,
                    content.get("instruction"),
                    content.get("phrase"),
                )
                if value
            )
        )
        if material_type in {"quantity_cards", "matching_page"} and count_labels:
            concept = f"{theme} themed countable classroom object"
            content["range"] = {
                "start": int(count_labels[0]),
                "end": int(count_labels[-1]),
            }
            return [
                {
                    "id": (
                        f"match-quantity-{label}"
                        if material_type == "matching_page"
                        else f"quantity-{label}"
                    ),
                    "label": label,
                    "quantity": int(label),
                    "assetRole": (
                        "matching_quantity"
                        if material_type == "matching_page"
                        else "countable_object"
                    ),
                    "concept": concept,
                    "prompt": base_prompt.format(concept=concept),
                    "imageAltText": f"{label} countable {theme} themed objects.",
                    "generationStatus": "not_started",
                }
                for label in count_labels
            ]

        role_by_type = {
            "quantity_cards": "countable_object",
            "number_cards": "theme_cue",
            "scenario_cards": "scenario",
            "sequence_cards": "sequence_step",
            "social_narrative": "scenario",
            "core_word_board": "communication_symbol",
            "visual_schedule": "sequence_step",
            "task_analysis_cards": "sequence_step",
            "emotion_scale": "regulation_level",
            "choice_board": "choice",
            "first_then_board": "sequence_step",
            "sorting_page": "sorting_item",
            "matching_page": "matching_item",
            "help_card": "communication_symbol",
            "break_card": "communication_symbol",
            "teacher_cue_card": "teacher_cue",
            "token_board": "reinforcer",
        }
        role = role_by_type.get(material_type, "instructional_visual")
        result: list[dict] = []
        for index, label in enumerate(labels[:6]):
            clean_label = " ".join(str(label).split())
            if not clean_label:
                continue
            item_concept = f"{clean_label}, {theme} classroom context"
            result.append(
                {
                    "id": f"{role}-{index + 1}",
                    "label": clean_label,
                    "assetRole": role,
                    "concept": item_concept,
                    "prompt": base_prompt.format(concept=item_concept),
                    "imageAltText": f"Illustration representing {clean_label}.",
                    "generationStatus": "not_started",
                }
            )
        return result

    @classmethod
    def _material_labels(
        cls,
        material_type: str,
        content: dict,
        draft: LessonDesignDraftDto,
    ) -> list[str]:
        if material_type == "number_cards":
            return cls._counting_labels(
                " ".join(
                    str(value)
                    for value in (
                        draft.goalText,
                        draft.observableResponse,
                        draft.theme,
                        content.get("instruction"),
                    )
                    if value
                )
            ) or ["1", "2", "3", "4", "5"]
        if material_type == "first_then_board":
            return [
                str(content.get("firstText") or "Practice the target skill"),
                str(content.get("thenText") or "Teacher-confirmed reward"),
            ]
        keys = {
            "scenario_cards": ("scenarios", "examples", "items"),
            "sequence_cards": ("steps", "examples", "items"),
            "social_narrative": ("responseOptions", "examples", "scenarios"),
            "core_word_board": ("words", "options", "examples"),
            "choice_board": ("options", "examples", "items"),
            "sorting_page": ("items", "examples", "categories"),
            "matching_page": ("items", "examples", "pairs"),
            "visual_schedule": ("steps", "examples", "items"),
            "task_analysis_cards": ("steps", "examples", "items"),
            "emotion_scale": ("levels", "examples", "items"),
        }.get(material_type, ())
        for key in keys:
            value = content.get(key)
            if isinstance(value, list) and value:
                return [str(item) for item in value]
        if material_type in {
            "scenario_cards",
            "sequence_cards",
            "social_narrative",
            "core_word_board",
            "choice_board",
            "sorting_page",
            "matching_page",
            "visual_schedule",
            "task_analysis_cards",
            "emotion_scale",
        } and draft.scenarios:
            return [str(item) for item in draft.scenarios]
        label = (
            content.get("phrase")
            or content.get("requestText")
            or content.get("reward")
            or content.get("instruction")
            or draft.observableResponse
            or draft.goalText
        )
        return [str(label)]

    @staticmethod
    def _counting_labels(text: str) -> list[str]:
        import re

        match = re.search(
            r"\b(\d{1,2})\s+(?:to|through|-)\s+(\d{1,2})\b", text, re.I
        )
        if not match:
            return []
        start, end = int(match.group(1)), int(match.group(2))
        if start < 1 or end < start or end > 10 or end - start > 9:
            return []
        return [str(number) for number in range(start, end + 1)]

    @classmethod
    def _default_material_definition(
        cls, material_type: str, draft: LessonDesignDraftDto
    ) -> dict:
        counting_labels = cls._counting_labels(
            " ".join(
                (
                    draft.goalText,
                    draft.observableResponse,
                    draft.theme,
                )
            )
        )
        blueprint = V2MaterialBlueprintService.blueprint(material_type)
        content: dict = {
            "instruction": draft.observableResponse or draft.goalText,
            "examples": draft.scenarios,
        }
        if material_type in {"quantity_cards", "number_cards"}:
            labels = counting_labels or ["1", "2", "3", "4", "5"]
            content.update(
                {
                    "range": {
                        "start": int(labels[0]),
                        "end": int(labels[-1]),
                    },
                    "instruction": (
                        "Identify or order the numerals."
                        if material_type == "number_cards"
                        else "Count the objects, then identify the numeral."
                    ),
                }
            )
        elif material_type == "matching_page" and counting_labels:
            content.update(
                {
                    "instruction": "Match each numeral to the same quantity.",
                    "pairs": [
                        {"left": label, "right": f"{label} objects"}
                        for label in counting_labels
                    ],
                    "answerKey": [
                        f"{label} → {label} objects" for label in counting_labels
                    ],
                }
            )
        elif material_type == "token_board":
            content.update(
                {
                    "tokenCount": 5,
                    "rewardLabel": "Teacher-confirmed choice",
                    "instruction": "Earn tokens, then access the selected reward.",
                }
            )
        elif material_type == "sequence_cards":
            content.update(
                {
                    "steps": draft.scenarios[:6]
                    or ["Get ready", "Practice the target", "Finish"],
                    "instruction": "Put the steps in order, then follow the sequence.",
                }
            )
        elif material_type == "social_narrative":
            content.update(
                {
                    "situation": draft.scenarios[0]
                    if draft.scenarios
                    else "A familiar teaching situation",
                    "responseOptions": [
                        draft.observableResponse or draft.goalText,
                        "Ask for help, more time, or a break",
                    ],
                    "supportOptions": [
                        "Use the learner's confirmed communication method",
                        "Use the teacher-confirmed visual or wait-time support",
                    ],
                    "instruction": "Review the situation and available response options.",
                }
            )
        elif material_type == "core_word_board":
            content.update(
                {
                    "words": ["Help", "More", "Stop", "Break", "Yes", "No"],
                    "responseModes": [
                        draft.responseLevel
                        or "Teacher-confirmed AAC, speech, sign, gesture, or pointing"
                    ],
                    "instruction": "Model and honor any intentional selection.",
                }
            )
        elif material_type == "data_sheet":
            content.update(
                {
                    "columns": [
                        "Opportunity",
                        "Independent",
                        "Prompt level",
                        "Outcome",
                        "Notes",
                    ],
                    "summaryCalculation": (
                        "Summarize independent and prompted outcomes separately."
                    ),
                }
            )
        elif material_type in {"summary_template", "session_summary"}:
            content.update(
                {
                    "prompts": [
                        "What worked?",
                        "What support was used?",
                        "What small win did you observe?",
                        "What is the next step?",
                    ]
                }
            )
        return {
            "type": material_type,
            "title": (
                blueprint.display_name
                if blueprint
                else material_type.replace("_", " ").title()
            ),
            "content": content,
        }

    @staticmethod
    def _build_material_specification(
        material_type: str, content: dict, draft: LessonDesignDraftDto
    ):
        blueprint = V2MaterialBlueprintService.blueprint(material_type)
        common = {
            "purpose": (
                blueprint.instructional_purpose
                if blueprint
                else f"Support the teacher-confirmed target: {draft.goalText}"
            ),
            "audience": "learner",
            "pageSize": "Letter",
            "orientation": (
                "landscape" if material_type == "token_board" else "portrait"
            ),
            "margins": "0.5 in print-safe margins",
            "textLimit": "One short direction and brief labels",
            "imageNeed": (
                "required"
                if material_type
                in {
                    "quantity_cards",
                    "number_cards",
                    "visual_card",
                    "choice_board",
                    "scenario_cards",
                    "sequence_cards",
                    "social_narrative",
                    "core_word_board",
                }
                else "optional"
            ),
            "contrastGuidance": "High contrast; do not rely on color alone",
            "printPreparation": [
                "Review wording",
                "Check margins",
                "Print at actual size",
            ],
            "editableFields": ["title", "instruction", "examples"],
            "requiredContent": list(blueprint.required_content) if blueprint else [],
            "professionalRules": (
                list(blueprint.professional_rules) if blueprint else []
            ),
            "teacherDirections": (
                list(blueprint.teacher_directions) if blueprint else []
            ),
            "altText": str(
                content.get("imageAltText") or "Teacher-reviewed instructional support"
            ),
        }
        response = draft.responseLevel or draft.observableResponse or draft.goalText
        if material_type in {"quantity_cards", "number_cards"}:
            labels = V2LessonPackageService._counting_labels(
                " ".join(
                    (
                        draft.goalText,
                        draft.observableResponse,
                        draft.theme,
                    )
                )
            ) or ["1", "2", "3", "4", "5"]
            if material_type == "number_cards":
                return NumberCardsSpecification(
                    **common,
                    rangeStart=int(labels[0]),
                    rangeEnd=int(labels[-1]),
                    includeThemeCue=True,
                )
            return QuantityCardsSpecification(
                **common,
                rangeStart=int(labels[0]),
                rangeEnd=int(labels[-1]),
                representationStyle="objects",
                includeNumerals=True,
            )
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
        if material_type == "sequence_cards":
            return SequenceCardsSpecification(
                **common,
                steps=(
                    [str(item) for item in content.get("steps", [])]
                    if isinstance(content.get("steps"), list)
                    else []
                )
                or draft.scenarios[:6]
                or ["Get ready", "Practice", "Finish"],
                numbered=True,
            )
        if material_type == "social_narrative":
            return SocialNarrativeSpecification(
                **common,
                situation=str(
                    content.get("situation")
                    or (draft.scenarios[0] if draft.scenarios else "Familiar situation")
                ),
                responseOptions=[
                    str(item)
                    for item in (
                        content.get("responseOptions")
                        if isinstance(content.get("responseOptions"), list)
                        else [draft.observableResponse or draft.goalText]
                    )
                ],
                supportOptions=[
                    str(item)
                    for item in (
                        content.get("supportOptions")
                        if isinstance(content.get("supportOptions"), list)
                        else ["Use a teacher-confirmed support"]
                    )
                ],
            )
        if material_type == "core_word_board":
            return CoreWordBoardSpecification(
                **common,
                words=[
                    str(item)
                    for item in (
                        content.get("words")
                        if isinstance(content.get("words"), list)
                        else ["Help", "More", "Stop", "Break", "Yes", "No"]
                    )
                ],
                responseModes=[
                    str(item)
                    for item in (
                        content.get("responseModes")
                        if isinstance(content.get("responseModes"), list)
                        else [draft.responseLevel or "Teacher-confirmed response mode"]
                    )
                ],
            )
        if material_type == "visual_schedule":
            return VisualScheduleSpecification(
                **common,
                steps=draft.scenarios[:6] or ["Start", "Practice", "Finish"],
                completionCue="Move completed step to Done",
            )
        if material_type == "task_analysis_cards":
            return TaskAnalysisCardsSpecification(
                **common,
                steps=draft.scenarios[:8] or ["Teacher confirms routine steps"],
            )
        if material_type == "emotion_scale":
            return EmotionScaleSpecification(
                **common,
                levels=["Calm", "Uncomfortable", "Need support"],
                regulationOptions=[
                    "Ask for a break",
                    "Use a teacher-confirmed regulation support",
                ],
            )
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
