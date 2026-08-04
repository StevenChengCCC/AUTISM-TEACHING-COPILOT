from __future__ import annotations

from hashlib import sha256
import json
import re

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    LessonPackageDto,
    LessonSpec,
    LessonSpecFieldResolution,
    MaterialApproval,
    MaterialCompatibilityCheck,
    MaterialRevisionImpact,
    NewMaterialImpact,
    NextSessionMaterialImpactPlanDto,
    NextSessionPlanOverride,
    PackageOptionalEnrichment,
    ProposedLessonSpecRevision,
    RecommendationFieldProvenance,
    ReusableMaterialImpact,
    SelectiveScenarioRegenerationRequest,
    UpdateNextSessionPlanRequest,
    utc_now,
)
from app.services.v2_instructional_constraint_service import (
    build_instructional_constraint_snapshot,
)
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_material_spec_service import V2MaterialSpecService
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_session_outcome_service import V2SessionOutcomeService
from app.services.v2_visual_asset_plan_service import V2VisualAssetPlanService

_CANONICAL_FIELDS = [
    "/goal/observableBehavior",
    "/goal/independenceDefinition",
    "/goal/successCriterion",
    "/duration",
    "/contexts",
    "/communicationPlan",
    "/promptingPlan",
    "/reinforcementPlan",
    "/transitionPlan",
    "/accessPlan",
    "/generalizationPlan",
    "/dataPlan",
    "/materialRequests",
    "/teacherEdits",
]

_MATERIAL_DEPENDENCIES = {
    "break_card": {"goal", "response_modes", "access"},
    "help_card": {"goal", "response_modes", "access"},
    "visual_timer": {"access"},
    "token_board": {"reinforcement", "access"},
    "first_then_board": {"contexts", "reinforcement", "access"},
    "scenario_cards": {"goal", "response_modes", "reinforcement", "contexts", "access"},
    "blue_line_activity": {"goal", "response_modes", "contexts", "access"},
    "data_sheet": {"goal", "response_modes", "contexts", "access"},
    "teacher_cue_card": {
        "goal",
        "response_modes",
        "reinforcement",
        "contexts",
        "access",
    },
    "summary_template": {
        "goal",
        "response_modes",
        "reinforcement",
        "contexts",
        "access",
    },
    "session_summary": {
        "goal",
        "response_modes",
        "reinforcement",
        "contexts",
        "access",
    },
}


class V2NextSessionWorkflowService:
    """Create immutable next-session revisions and selectively clone artifacts."""

    def __init__(self, repos: V2Repositories = repositories):
        self.repos = repos
        self.material_specs = V2MaterialSpecService()
        self.visual_plans = V2VisualAssetPlanService()

    def create_plan(
        self, package_id: str, expected_package_revision: int
    ) -> NextSessionMaterialImpactPlanDto:
        package = self._package(package_id)
        if package.version != expected_package_revision:
            raise ConflictError(
                "The prior package changed after this page loaded. Refresh before planning the next session."
            )
        if package.lessonSpec is None:
            raise ValidationError("The prior package has no typed LessonSpec")
        goal_id = V2SessionOutcomeService.goal_id(package.lessonSpec)
        recommendations = sorted(
            [
                item
                for item in self.repos.next_session_recommendations.list()
                if item.learnerId == package.learnerId
                and item.goalId == goal_id
                and item.status in {"accepted", "edited"}
            ],
            key=lambda item: item.id,
        )
        fingerprint = sha256(
            json.dumps(
                {
                    "packageId": package.id,
                    "packageRevision": package.version,
                    "recommendations": [
                        (item.id, item.version, item.status) for item in recommendations
                    ],
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        plan_id = f"next-session-plan-{fingerprint[:24]}"
        existing = self.repos.next_session_impact_plans.get(plan_id)
        if existing is not None:
            return existing

        proposed, blocking = self._propose_lesson_spec(
            package, recommendations, fingerprint
        )
        reusable, revise, new, material_blocking = self._analyze_materials(
            package, proposed.lessonSpec, recommendations
        )
        blocking.extend(material_blocking)
        plan = NextSessionMaterialImpactPlanDto(
            id=plan_id,
            learnerId=package.learnerId,
            previousPackageId=package.id,
            previousPackageRevision=package.version,
            proposedLessonSpecId=proposed.lessonSpec.id,
            proposedLessonSpecRevision=proposed,
            reusableMaterials=reusable,
            materialsToRevise=revise,
            newMaterialsRequired=new,
            materialsToRemove=[],
            blockingIssues=blocking,
        )
        return self.repos.next_session_impact_plans.save(plan)

    def get_plan(self, plan_id: str) -> NextSessionMaterialImpactPlanDto:
        plan = self.repos.next_session_impact_plans.get(plan_id)
        if plan is None:
            raise NotFoundError("Next-session impact plan not found")
        return plan

    def update_plan(
        self, plan_id: str, request: UpdateNextSessionPlanRequest
    ) -> NextSessionMaterialImpactPlanDto:
        plan = self.get_plan(plan_id)
        if plan.version != request.expectedVersion:
            raise ConflictError("The impact plan changed. Refresh before editing it.")
        if plan.status != "proposed":
            raise ConflictError(
                "A package-created impact plan can no longer be changed"
            )
        reusable = list(plan.reusableMaterials)
        revise = list(plan.materialsToRevise)
        new = list(plan.newMaterialsRequired)
        if request.action == "force_regenerate":
            source = next(
                (item for item in reusable if item.materialId == request.materialId),
                None,
            )
            if source is None:
                raise ValidationError("Select a currently reusable material")
            reusable = [
                item for item in reusable if item.materialId != source.materialId
            ]
            revise.append(
                MaterialRevisionImpact(
                    materialId=source.materialId,
                    materialRevision=source.materialRevision,
                    materialType=source.materialType,
                    title=source.title,
                    affectedFields=[],
                    reason=f"Teacher requested regeneration: {request.reason}",
                    compatibilityChecks=source.compatibilityChecks,
                    safeToKeepExisting=True,
                )
            )
        elif request.action == "keep_existing":
            source = next(
                (item for item in revise if item.materialId == request.materialId), None
            )
            if source is None:
                raise ValidationError("Select a material currently marked for revision")
            if not source.safeToKeepExisting or not all(
                item.passed for item in source.compatibilityChecks
            ):
                raise ConflictError(
                    "This material has a semantic or safety incompatibility and cannot be kept unchanged"
                )
            revise = [item for item in revise if item.materialId != source.materialId]
            reusable.append(
                ReusableMaterialImpact(
                    materialId=source.materialId,
                    materialRevision=source.materialRevision,
                    materialType=source.materialType,
                    title=source.title,
                    reasonReusable=f"Teacher kept the semantically compatible material: {request.reason}",
                    compatibilityChecks=source.compatibilityChecks,
                )
            )
        else:
            source = next(
                (item for item in new if item.materialType == request.materialType),
                None,
            )
            if source is None:
                raise ValidationError("Select an automatically proposed new material")
            if source.required:
                raise ConflictError(
                    "A required material cannot be rejected from this plan"
                )
            new = [item for item in new if item.materialType != source.materialType]
        override = NextSessionPlanOverride(
            action=request.action,
            materialId=request.materialId,
            materialType=request.materialType,
            reason=request.reason,
        )
        return self.repos.next_session_impact_plans.save(
            plan.model_copy(
                update={
                    "reusableMaterials": reusable,
                    "materialsToRevise": revise,
                    "newMaterialsRequired": new,
                    "overrides": [*plan.overrides, override],
                }
            )
        )

    def create_package(
        self, plan_id: str, expected_plan_version: int
    ) -> LessonPackageDto:
        plan = self.get_plan(plan_id)
        if plan.version != expected_plan_version:
            raise ConflictError(
                "The impact plan changed. Refresh before creating the kit."
            )
        if plan.createdPackageId:
            return self._package(plan.createdPackageId)
        if plan.blockingIssues:
            raise ConflictError(
                "Resolve blocking impact issues before creating the next kit"
            )
        previous = self._package(plan.previousPackageId)
        proposed = plan.proposedLessonSpecRevision.lessonSpec
        new_package_id = self.repos.next_id("package")
        reusable_ids = {item.materialId for item in plan.reusableMaterials}
        revise_by_id = {item.materialId: item for item in plan.materialsToRevise}
        removed_ids = {item.materialId for item in plan.materialsToRemove}
        cloned_materials = []
        for material in previous.materials:
            if material.id in removed_ids:
                continue
            if material.id in reusable_ids:
                cloned_materials.append(
                    self._clone_reusable(material, new_package_id, proposed)
                )
            elif material.id in revise_by_id:
                cloned_materials.append(
                    self._regenerate_clone(
                        material,
                        new_package_id,
                        proposed,
                        revise_by_id[material.id],
                        plan,
                    )
                )
            else:
                # A material can only reach this branch when an unsupported legacy
                # type could not be analyzed safely.
                raise ConflictError(f"No impact decision exists for {material.title}")
        for addition in plan.newMaterialsRequired:
            cloned_materials.append(
                self._generate_new_material(new_package_id, proposed, addition)
            )
        content_plan = previous.packageContentPlan
        if content_plan is not None:
            optional_types = {
                item.material_type for item in content_plan.optional_enrichments
            }
            additions = [
                PackageOptionalEnrichment(
                    materialType=item.materialType,
                    reasonSuggested=item.reason,
                    defaultIncluded=True,
                )
                for item in plan.newMaterialsRequired
                if item.materialType not in optional_types
            ]
            content_plan = content_plan.model_copy(
                update={
                    "id": f"content-plan-{new_package_id}",
                    "lesson_spec_id": proposed.id,
                    "lesson_spec_revision": proposed.revision,
                    "optional_enrichments": [
                        *content_plan.optional_enrichments,
                        *additions,
                    ],
                    "estimated_artifact_count": len(cloned_materials),
                }
            )
        created = previous.model_copy(
            deep=True,
            update={
                "id": new_package_id,
                "draftId": f"next-{previous.draftId}",
                "materials": cloned_materials,
                "lessonSpec": proposed,
                "packageContentPlan": content_plan,
                "profileRevision": proposed.profile_revision,
                "goal": proposed.goal.display_text,
                "targetSkill": proposed.goal.display_text,
                "observableResponse": proposed.goal.observable_behavior,
                "objective": proposed.goal.display_text,
                "responseModality": ", ".join(proposed.goal.accepted_response_modes),
                "documentContent": {
                    **previous.documentContent,
                    "previousPackageId": previous.id,
                    "nextSessionImpactPlanId": plan.id,
                    "acceptedRecommendationIds": plan.proposedLessonSpecRevision.acceptedRecommendationIds,
                },
                "staleOutputs": [item.materialType for item in plan.materialsToRevise],
                "status": "teacher_review_needed",
                "validationStatus": "pending",
                "validatedRevision": None,
                "validatedLessonSpecRevision": None,
                "version": 1,
            },
        )
        with self.repos.transaction():
            # Production SQL enforces the material -> package foreign key.
            # The package snapshot already contains these same material values.
            saved_package = self.repos.lesson_packages.save(created)
            for material in cloned_materials:
                self.repos.generated_materials.save(material)
            self.repos.next_session_impact_plans.save(
                plan.model_copy(
                    update={
                        "status": "package_created",
                        "createdPackageId": saved_package.id,
                    }
                )
            )
        return saved_package

    def regenerate_material(
        self, package_id: str, material_id: str, expected_material_version: int
    ) -> GeneratedMaterialDto:
        package = self._package(package_id)
        material = self._material(material_id, package_id)
        if material.version != expected_material_version:
            raise ConflictError("The material changed. Refresh before regenerating it.")
        if package.lessonSpec is None:
            raise ValidationError("The next-session package has no LessonSpec")
        impact = MaterialRevisionImpact(
            materialId=material.id,
            materialRevision=(
                material.materialSpec.revision if material.materialSpec else 1
            ),
            materialType=material.type,
            title=material.title,
            reason="Teacher selectively regenerated this material.",
        )
        candidate = self._regenerate_clone(
            material, package.id, package.lessonSpec, impact, None, preserve_id=True
        )
        candidate = candidate.model_copy(update={"version": material.version})
        return V2MaterialService(self.repos)._save_generated(candidate)

    def regenerate_scenario(
        self,
        package_id: str,
        material_id: str,
        request: SelectiveScenarioRegenerationRequest,
    ) -> GeneratedMaterialDto:
        package = self._package(package_id)
        material = self._material(material_id, package_id)
        if material.version != request.expectedMaterialVersion:
            raise ConflictError(
                "The scenario material changed. Refresh before regenerating it."
            )
        if material.type != "scenario_cards" or material.materialSpec is None:
            raise ValidationError("Select a typed scenario-card material")
        scenarios = list(material.materialSpec.content.scenarios)
        index = next(
            (
                index
                for index, item in enumerate(scenarios)
                if item.id == request.scenarioId
            ),
            None,
        )
        if index is None:
            raise NotFoundError("Scenario card not found")
        instruction = request.teacherInstruction.strip()
        revised_scenario = scenarios[index].model_copy(
            update={
                "teacher_wording": instruction or scenarios[index].teacher_wording,
            }
        )
        scenarios[index] = revised_scenario
        content = material.materialSpec.content.model_copy(
            update={"scenarios": scenarios}
        )
        payload = material.content | content.model_dump(mode="json", by_alias=True)
        material_service = V2MaterialService(self.repos)
        candidate = material_service._prepare_material_edit(
            material,
            {
                "content": payload,
                "version": material.version,
            },
        )
        candidate = self._preserve_unaffected_visuals(
            material, candidate, affected_context_ids={request.scenarioId}
        )
        return material_service._save_generated(candidate)

    def _propose_lesson_spec(self, package, recommendations, fingerprint):
        previous = package.lessonSpec
        assert previous is not None
        learner = self.repos.learners.get(package.learnerId)
        record_repo = self.repos.records
        records = (
            record_repo.for_learner(package.learnerId)
            if hasattr(record_repo, "for_learner")
            else record_repo.list_for_learner(package.learnerId)
        )
        snapshot = build_instructional_constraint_snapshot(learner, records)
        blocking = []
        if snapshot.profile_revision != previous.profile_revision:
            blocking.append(
                "The learner profile revision changed after the prior package. Review the updated profile before reusing materials."
            )
        changed = []
        field_provenance = []
        teacher_edits = list(previous.teacher_edits)
        prompt = previous.prompting_plan
        generalization = previous.generalization_plan
        goal = previous.goal
        duration = previous.duration
        resolutions = list(previous.provenance.field_resolutions)
        teacher_authored = list(previous.provenance.teacher_authored_fields)
        teacher_selected = list(previous.provenance.teacher_selected_fields)
        for recommendation in recommendations:
            content = (
                recommendation.teacherEditedText
                if recommendation.status == "edited"
                else recommendation.recommendation
            )
            teacher_edits.append(content)
            self._append(changed, "/teacherEdits")
            source = (
                "teacher_authored"
                if recommendation.status == "edited"
                else "teacher_selected"
            )
            if recommendation.status == "edited":
                self._append(teacher_authored, "/teacherEdits")
            else:
                self._append(teacher_selected, "/teacherEdits")
            applied_paths = []
            if recommendation.type == "prompt_fading":
                prompt = prompt.model_copy(
                    update={
                        "fade_rule": f"{prompt.fade_rule} Next-session review: {content}"
                    }
                )
                applied_paths.append("/promptingPlan/fadeRule")
            if recommendation.type in {"add_generalization", "change_context"}:
                context_label = next(
                    (
                        item.contextLabel
                        for item in recommendation.evidence
                        if item.contextLabel
                    ),
                    None,
                )
                if context_label:
                    contexts = sorted(
                        generalization.contexts,
                        key=lambda item: 0 if item.label == context_label else 1,
                    )
                    generalization = generalization.model_copy(
                        update={"contexts": contexts}
                    )
                    applied_paths.append("/generalizationPlan/contexts")
            if recommendation.type == "adjust_duration":
                minutes = next(
                    (int(item) for item in re.findall(r"\d+", content)), None
                )
                if minutes is not None:
                    duration = duration.model_copy(
                        update={
                            "maximum_activity_block_minutes": max(1, min(120, minutes))
                        }
                    )
                    applied_paths.append("/duration/maximumActivityBlockMinutes")
            for path in recommendation.affectedLessonSpecPaths:
                normalized = path.casefold()
                if normalized.endswith("/observablebehavior"):
                    goal = goal.model_copy(update={"observable_behavior": content})
                    applied_paths.append("/goal/observableBehavior")
                elif normalized.endswith("/independencedefinition"):
                    goal = goal.model_copy(update={"independence_definition": content})
                    applied_paths.append("/goal/independenceDefinition")
            for path in list(
                dict.fromkeys([*recommendation.affectedLessonSpecPaths, *applied_paths])
            ):
                actually_changed = path in applied_paths
                field_provenance.append(
                    RecommendationFieldProvenance(
                        fieldPath=path,
                        recommendationId=recommendation.id,
                        recommendationStatus=recommendation.status,
                        sourceContent=content,
                        appliedValue=content if actually_changed else None,
                        changed=actually_changed,
                    )
                )
                if actually_changed:
                    self._append(changed, path)
                    resolutions.append(
                        LessonSpecFieldResolution(
                            fieldPath=path,
                            source=source,
                            reason=f"Teacher-{recommendation.status} next-session recommendation {recommendation.id}.",
                        )
                    )
        provenance = previous.provenance.model_copy(
            update={
                "teacher_authored_fields": teacher_authored,
                "teacher_selected_fields": teacher_selected,
                "field_resolutions": resolutions,
            }
        )
        proposed = previous.model_copy(
            deep=True,
            update={
                "id": f"lesson-spec-next-{fingerprint[:24]}",
                "revision": previous.revision + 1,
                "profile_revision": snapshot.profile_revision,
                "teacher_edits": teacher_edits,
                "goal": goal,
                "duration": duration,
                "prompting_plan": prompt,
                "generalization_plan": generalization,
                "provenance": provenance,
            },
        )
        previous_key = V2SessionOutcomeService.goal_comparison_key(previous)
        proposed_key = V2SessionOutcomeService.goal_comparison_key(proposed)
        boundary = "continue" if previous_key == proposed_key else "new"
        return (
            ProposedLessonSpecRevision(
                id=f"proposed-revision-{fingerprint[:24]}",
                previousLessonSpecId=previous.id,
                previousLessonSpecRevision=previous.revision,
                lessonSpec=proposed,
                acceptedRecommendationIds=[item.id for item in recommendations],
                teacherEditedRecommendationContent={
                    item.id: item.teacherEditedText
                    for item in recommendations
                    if item.status == "edited" and item.teacherEditedText is not None
                },
                changedFields=changed,
                unchangedFields=[
                    item for item in _CANONICAL_FIELDS if item not in changed
                ],
                proposedGoalId=V2SessionOutcomeService.goal_id(proposed),
                proposedGoalRevision=proposed.revision,
                goalSeriesBoundary=boundary,
                profileRevision=proposed.profile_revision,
                fieldProvenance=field_provenance,
            ),
            blocking,
        )

    def _analyze_materials(self, package, proposed, recommendations):
        reusable = []
        revise = []
        material_types = {item.type for item in package.materials}
        new = []
        blocking = []
        for recommendation in recommendations:
            for material_type in recommendation.affectedMaterialTypes:
                if material_type not in material_types and material_type != "unknown":
                    supported = (
                        self.material_specs.build(
                            material_id="impact-preview-material",
                            package_id=package.id,
                            material_type=material_type,
                            title=material_type.replace("_", " ").title(),
                            lesson_spec=proposed,
                        )
                        is not None
                    )
                    if supported:
                        new.append(
                            NewMaterialImpact(
                                materialType=material_type,
                                reason=f"Accepted recommendation {recommendation.id} references a material not present in the prior package.",
                                recommendationIds=[recommendation.id],
                                required=False,
                            )
                        )
                    else:
                        blocking.append(
                            f"Accepted recommendation {recommendation.id} requests unsupported material type {material_type}."
                        )
        for material in package.materials:
            checks = self._compatibility_checks(material, package.lessonSpec, proposed)
            direct = [
                item
                for item in recommendations
                if material.id in item.affectedMaterialIds
                or material.type in item.affectedMaterialTypes
            ]
            direct_changes = [item for item in direct if item.type != "reuse"]
            affected_fields = list(
                dict.fromkeys(
                    path for item in direct for path in item.affectedLessonSpecPaths
                )
            )
            changed_paths = self._material_changed_paths(
                material.type, package.lessonSpec, proposed
            )
            affected_fields = list(dict.fromkeys([*affected_fields, *changed_paths]))
            all_compatible = all(item.passed for item in checks)
            if direct_changes or changed_paths or not all_compatible:
                reasons = []
                if direct_changes:
                    reasons.append(
                        "Accepted recommendation explicitly affects this material"
                    )
                if changed_paths:
                    reasons.append(
                        "Proposed LessonSpec fields used by this material changed: "
                        + ", ".join(changed_paths)
                    )
                reasons.extend(item.detail for item in checks if not item.passed)
                revise.append(
                    MaterialRevisionImpact(
                        materialId=material.id,
                        materialRevision=(
                            material.materialSpec.revision
                            if material.materialSpec
                            else material.version
                        ),
                        materialType=material.type,
                        title=material.title,
                        affectedFields=affected_fields,
                        reason="; ".join(reasons),
                        recommendationIds=[item.id for item in direct_changes],
                        compatibilityChecks=checks,
                        safeToKeepExisting=all_compatible,
                    )
                )
            else:
                reusable.append(
                    ReusableMaterialImpact(
                        materialId=material.id,
                        materialRevision=(
                            material.materialSpec.revision
                            if material.materialSpec
                            else material.version
                        ),
                        materialType=material.type,
                        title=material.title,
                        reasonReusable=(
                            "Goal, response modes, reinforcement, context dependencies, access constraints, profile revision, visual constraints, semantic content, and exact approval lineage remain compatible."
                        ),
                        recommendationIds=[item.id for item in direct],
                        compatibilityChecks=checks,
                    )
                )
        return (
            reusable,
            revise,
            list({item.materialType: item for item in new}.values()),
            list(dict.fromkeys(blocking)),
        )

    def _compatibility_checks(self, material, previous, proposed):
        dependencies = _MATERIAL_DEPENDENCIES.get(
            material.type,
            {"goal", "response_modes", "reinforcement", "contexts", "access"},
        )
        values = {
            "goal": previous.goal == proposed.goal,
            "response_modes": previous.communication_plan
            == proposed.communication_plan,
            "reinforcement": previous.reinforcement_plan == proposed.reinforcement_plan,
            "contexts": previous.contexts == proposed.contexts,
            "access": previous.access_plan == proposed.access_plan,
        }
        checks = [
            MaterialCompatibilityCheck(
                dimension=dimension,
                passed=(values[dimension] if dimension in dependencies else True),
                detail=(
                    f"Relevant {dimension.replace('_', ' ')} semantics are unchanged."
                    if dimension not in dependencies or values[dimension]
                    else f"Relevant {dimension.replace('_', ' ')} semantics changed."
                ),
            )
            for dimension in (
                "goal",
                "response_modes",
                "reinforcement",
                "contexts",
                "access",
            )
        ]
        checks.append(
            MaterialCompatibilityCheck(
                dimension="profile_revision",
                passed=previous.profile_revision == proposed.profile_revision,
                detail=(
                    "Learner profile revision matches."
                    if previous.profile_revision == proposed.profile_revision
                    else "Learner profile revision changed."
                ),
            )
        )
        approval_valid = bool(
            material.materialSpec
            and material.materialSpec.approval.status == "approved"
            and material.materialSpec.approval.approved_revision
            == material.materialSpec.revision
        )
        checks.append(
            MaterialCompatibilityCheck(
                dimension="approval",
                passed=approval_valid,
                detail=(
                    "Exact material revision is approved."
                    if approval_valid
                    else "Exact material revision is not approved."
                ),
            )
        )
        candidate = (
            self.material_specs.build(
                material_id=material.id,
                package_id=material.packageId,
                material_type=material.type,
                title=material.title,
                lesson_spec=proposed,
            )
            if material.materialSpec is not None
            else None
        )
        visual_same = bool(
            candidate
            and candidate.design_constraints == material.materialSpec.design_constraints
        )
        semantic_same = bool(
            candidate and candidate.content == material.materialSpec.content
        )
        checks.extend(
            [
                MaterialCompatibilityCheck(
                    dimension="visual_constraints",
                    passed=visual_same,
                    detail=(
                        "Visual and access constraints match."
                        if visual_same
                        else "Visual or access constraints changed."
                    ),
                ),
                MaterialCompatibilityCheck(
                    dimension="semantic_content",
                    passed=semantic_same,
                    detail=(
                        "Typed material semantics are unchanged."
                        if semantic_same
                        else "Typed material semantics changed under the proposed LessonSpec."
                    ),
                ),
            ]
        )
        return checks

    @staticmethod
    def _material_changed_paths(material_type, previous, proposed):
        paths = []
        if previous.prompting_plan != proposed.prompting_plan and material_type in {
            "teacher_cue_card",
            "scenario_cards",
            "data_sheet",
            "summary_template",
            "session_summary",
        }:
            paths.append("/promptingPlan")
        if (
            previous.generalization_plan != proposed.generalization_plan
            and material_type
            in {
                "scenario_cards",
                "data_sheet",
                "teacher_cue_card",
                "summary_template",
                "session_summary",
            }
        ):
            paths.append("/generalizationPlan")
        if previous.goal != proposed.goal:
            paths.append("/goal")
        return paths

    def _clone_reusable(self, material, package_id, lesson_spec):
        new_id = self.repos.next_id("material")
        spec = (
            material.materialSpec.model_copy(
                deep=True,
                update={
                    "id": f"material-spec-{new_id}",
                    "package_id": package_id,
                    "lesson_spec_id": lesson_spec.id,
                    "lesson_spec_revision": lesson_spec.revision,
                    "source_material_id": material.id,
                },
            )
            if material.materialSpec
            else None
        )
        plan = (
            material.visualAssetPlan.model_copy(
                deep=True,
                update={
                    # Visual plans are version-bound to MaterialSpec identity,
                    # not to the generated-material repository ID.
                    "material_id": spec.id if spec is not None else new_id,
                },
            )
            if material.visualAssetPlan
            else None
        )
        return material.model_copy(
            deep=True,
            update={
                "id": new_id,
                "packageId": package_id,
                "version": 1,
                "materialSpec": spec,
                "visualAssetPlan": plan,
            },
        )

    def _regenerate_clone(
        self,
        material,
        package_id,
        lesson_spec,
        impact,
        plan,
        *,
        preserve_id=False,
    ):
        new_id = material.id if preserve_id else self.repos.next_id("material")
        spec = self.material_specs.build(
            material_id=new_id,
            package_id=package_id,
            material_type=material.type,
            title=material.title,
            lesson_spec=lesson_spec,
        )
        if spec is None:
            raise ConflictError(
                f"{material.title} cannot be selectively regenerated from a typed schema"
            )
        old_revision = (
            material.materialSpec.revision
            if material.materialSpec
            else material.version
        )
        spec = spec.model_copy(
            update={
                "revision": old_revision + 1,
                "lesson_spec_id": lesson_spec.id,
                "lesson_spec_revision": lesson_spec.revision,
                "source_material_id": material.id,
                "approval": MaterialApproval(),
            }
        )
        visual = self.visual_plans.build(spec)
        candidate = material.model_copy(
            deep=True,
            update={
                "id": new_id,
                "packageId": package_id,
                "version": material.version if preserve_id else 1,
                "status": "teacher_review_needed",
                "materialSpec": spec,
                "visualAssetPlan": visual,
            },
        )
        affected_context_ids = set()
        if plan is not None:
            recommendation_ids = set(impact.recommendationIds)
            recommendations = [
                item
                for item in self.repos.next_session_recommendations.list()
                if item.id in recommendation_ids
            ]
            affected_context_ids = {
                evidence.contextId
                for item in recommendations
                for evidence in item.evidence
                if evidence.contextId
            }
        candidate = self._preserve_unaffected_visuals(
            material, candidate, affected_context_ids=affected_context_ids
        )
        projection = self.material_specs.render_projection(spec, material.content)
        if candidate.visualAssetPlan is not None:
            projection["visualItems"] = self.visual_plans.to_renderer_items(
                candidate.visualAssetPlan
            )
        semantic = self.material_specs.validate(spec, lesson_spec, projection)
        safety = self.material_specs.validate_safety(
            spec, lesson_spec, semantic, projection
        )
        spec = spec.model_copy(
            update={
                "semantic_validation": semantic,
                "safety_validation": safety,
            }
        )
        status = (
            "validation_failed"
            if semantic.status != "passed"
            else (
                "safety_review_needed"
                if safety.status != "passed"
                else "teacher_review_needed"
            )
        )
        return candidate.model_copy(
            update={
                "content": projection,
                "materialSpec": spec,
                "status": status,
            }
        )

    def _generate_new_material(self, package_id, lesson_spec, impact):
        material_id = self.repos.next_id("material")
        title = impact.materialType.replace("_", " ").title()
        spec = self.material_specs.build(
            material_id=material_id,
            package_id=package_id,
            material_type=impact.materialType,
            title=title,
            lesson_spec=lesson_spec,
        )
        if spec is None:
            raise ConflictError(
                f"The proposed new material type {impact.materialType} has no typed generation schema"
            )
        visual = self.visual_plans.build(spec)
        projection = self.material_specs.render_projection(spec, {})
        if visual is not None:
            projection["visualItems"] = self.visual_plans.to_renderer_items(visual)
        semantic = self.material_specs.validate(spec, lesson_spec, projection)
        safety = self.material_specs.validate_safety(
            spec, lesson_spec, semantic, projection
        )
        spec = spec.model_copy(
            update={
                "semantic_validation": semantic,
                "safety_validation": safety,
            }
        )
        status = (
            "validation_failed"
            if semantic.status != "passed"
            else (
                "safety_review_needed"
                if safety.status != "passed"
                else "teacher_review_needed"
            )
        )
        return GeneratedMaterialDto(
            id=material_id,
            packageId=package_id,
            type=impact.materialType,
            title=title,
            status=status,
            content=projection,
            printLayout={
                "pageSize": spec.design_constraints.page_size,
                "orientation": spec.design_constraints.orientation,
                "color": "blue",
            },
            materialSchemaVersion=1,
            materialSpec=spec,
            visualAssetPlan=visual,
        )

    @staticmethod
    def _preserve_unaffected_visuals(old, candidate, affected_context_ids):
        if old.visualAssetPlan is None or candidate.visualAssetPlan is None:
            return candidate
        old_by_key = {
            item.semantic_key: item for item in old.visualAssetPlan.visual_items
        }
        items = []
        for item in candidate.visualAssetPlan.visual_items:
            prior = old_by_key.get(item.semantic_key)
            affected = any(
                context_id in item.semantic_key for context_id in affected_context_ids
            )
            if prior is not None and not affected:
                item = item.model_copy(
                    update={
                        "status": prior.status,
                        "asset_id": prior.asset_id,
                        "fallback_asset_id": prior.fallback_asset_id,
                        "review_status": prior.review_status,
                    }
                )
            items.append(item)
        return candidate.model_copy(
            update={
                "visualAssetPlan": candidate.visualAssetPlan.model_copy(
                    update={"visual_items": items}
                )
            }
        )

    def _package(self, package_id):
        package = self.repos.lesson_packages.get(package_id)
        if package is None or not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        return package

    def _material(self, material_id, package_id):
        material = self.repos.generated_materials.get(material_id)
        if material is None or not isinstance(material, GeneratedMaterialDto):
            raise NotFoundError("Generated material not found")
        if material.packageId != package_id:
            raise ConflictError("Material belongs to a different lesson package")
        return material

    @staticmethod
    def _append(values, item):
        if item not in values:
            values.append(item)
