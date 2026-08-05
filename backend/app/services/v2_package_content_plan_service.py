from __future__ import annotations

from app.core.config import Settings, settings
from app.core.exceptions import ConflictError, ValidationError
from app.schemas.v2_dto import (
    LessonMaterialConfigurationEntry,
    LessonSpec,
    LessonSpecMaterialRequest,
    PackageContentPlan,
    PackageCoreMaterial,
    PackageExcludedMaterial,
    PackageOptionalEnrichment,
    PackageRequiredCompanion,
)
from app.services.v2_material_blueprint_service import V2MaterialBlueprintService


class V2PackageContentPlanService:
    """Deterministic completeness planning between LessonSpec and generation."""

    companion_rule_registry = {
        "functional_communication": "_communication_companions",
        "transition": "_transition_companions",
        "token_reinforcement": "_token_companions",
        "personalized_activity": "_activity_companions",
        "generalization": "_generalization_companions",
    }
    page_estimates = {
        "blue_line_activity": 3,
        "scenario_cards": 3,
        "data_sheet": 2,
        "summary_template": 2,
        "session_summary": 2,
    }
    additional_supported_materials = {
        "visual_timer": "Visual Timer",
        "blue_line_activity": "Personalized Instructional Activity",
    }

    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def build(self, lesson_spec: LessonSpec) -> PackageContentPlan:
        supported = [item for item in lesson_spec.material_requests if item.supported]
        excluded = [
            PackageExcludedMaterial(
                materialType=item.material_type,
                reasonExcluded=item.unsupported_reason or "This requested material is not supported and will not be silently replaced.",
                profileFactorIds=item.profile_factor_ids,
            )
            for item in lesson_spec.material_requests
            if not item.supported
        ]
        core = [
            PackageCoreMaterial(
                materialRequestId=item.request_id,
                materialType=item.material_type,
                reason=item.instructional_purpose or "Teacher selected this as a required core material.",
                decisionIds=lesson_spec.decision_ids,
                profileFactorIds=item.profile_factor_ids,
            )
            for item in supported
        ]
        plan = PackageContentPlan(
            id=f"content-plan-{lesson_spec.id}", lessonSpecId=lesson_spec.id,
            lessonSpecRevision=lesson_spec.revision,
            teacherSelectedCore=core, excludedMaterials=excluded,
        )
        for rule_name in self.companion_rule_registry.values():
            getattr(self, rule_name)(lesson_spec, plan)
        self._add_contextual_enrichments(lesson_spec, plan)
        return self.recompute(plan)

    def adjust(
        self,
        plan: PackageContentPlan,
        *,
        action: str,
        material_type: str,
        included: bool,
    ) -> PackageContentPlan:
        if action == "set_optional":
            item = next((value for value in plan.optional_enrichments if value.material_type == material_type), None)
            if item is None:
                raise ValidationError("Optional material is not part of this package plan")
            item.default_included = included
            if not included:
                self._rebalance_optionals(plan, exclude=material_type)
        elif action == "set_companion":
            item = next((value for value in plan.required_companions if value.material_type == material_type), None)
            if item is None:
                raise ValidationError("Required companion is not part of this package plan")
            if not included and not item.can_teacher_remove:
                raise ConflictError(item.removal_warning or "This companion is required for a semantically complete package")
            item.included = included
            if not included:
                self._rebalance_optionals(plan)
        elif action == "add_material":
            if not self._is_supported(material_type):
                raise ValidationError("The requested additional material type is not supported")
            if material_type in self._all_types(plan):
                for item in plan.optional_enrichments:
                    if item.material_type == material_type:
                        item.default_included = True
                return self.recompute(plan)
            plan.optional_enrichments.append(PackageOptionalEnrichment(
                materialType=material_type,
                reasonSuggested="Teacher added this supported material during package preview.",
                defaultIncluded=True,
                estimatedPages=self._pages(material_type),
            ))
        else:
            raise ValidationError("Unsupported package-plan action")
        return self.recompute(plan)

    def validate(self, plan: PackageContentPlan, lesson_spec: LessonSpec) -> PackageContentPlan:
        issues: list[str] = []
        if plan.lesson_spec_id != lesson_spec.id or plan.lesson_spec_revision != lesson_spec.revision:
            issues.append("Package content plan is stale for the current LessonSpec revision")
        selected = {item.material_type for item in lesson_spec.material_requests if item.supported}
        core = {item.material_type for item in plan.teacher_selected_core}
        if not selected.issubset(core):
            issues.append("Teacher-selected materials were removed from the package content plan")
        included = self.included_types(plan)
        excluded = {item.material_type for item in plan.excluded_materials}
        if included & excluded:
            issues.append("An excluded or unsupported material is included in the package")
        text = self._goal_text(lesson_spec)
        communication = self._is_communication_goal(text)
        transition = self._is_transition_goal(lesson_spec, text)
        compact_concept = self._is_compact_concept_package(lesson_spec, included)
        if communication:
            communication_types = {"help_card", "break_card", "scenario_cards", "blue_line_activity"}
            if not included & communication_types or "data_sheet" not in included:
                issues.append("The communication goal lacks a material to practice and record the response")
        if transition and not included & {"first_then_board", "visual_timer", "teacher_cue_card", "visual_schedule"}:
            issues.append("The transition lesson has no transition support")
        if "token_board" in included:
            reinforcement = lesson_spec.reinforcement_plan
            if not reinforcement.earned_reward:
                issues.append("The token board has no named pictured earned reward")
        if "blue_line_activity" in included and not lesson_spec.contexts:
            issues.append("The personalized activity has no executable context or required components")
        if lesson_spec.generalization_plan.required:
            required = max(3, lesson_spec.goal.success_criterion.required_contexts)
            if len(lesson_spec.contexts) < required or "scenario_cards" not in included:
                issues.append("Required generalization has fewer than three contexts or no scenario material")
        recomputed = self.recompute(plan)
        mandatory_types = {
            *[item.material_type for item in plan.teacher_selected_core],
            *[item.material_type for item in plan.required_companions if item.included],
        }
        mandatory_pages = sum(self._pages(item) for item in mandatory_types)
        artifact_outside = not self.config.PACKAGE_PLAN_MIN_ARTIFACTS <= recomputed.estimated_artifact_count <= self.config.PACKAGE_PLAN_MAX_ARTIFACTS
        if artifact_outside and not compact_concept and not (
            recomputed.estimated_artifact_count > self.config.PACKAGE_PLAN_MAX_ARTIFACTS
            and len(mandatory_types) > self.config.PACKAGE_PLAN_MAX_ARTIFACTS
        ):
            issues.append("Package artifact count is outside configured bounds")
        page_outside = not self.config.PACKAGE_PLAN_MIN_PAGES <= recomputed.estimated_page_count <= self.config.PACKAGE_PLAN_MAX_PAGES
        if page_outside and not compact_concept and not (
            recomputed.estimated_page_count > self.config.PACKAGE_PLAN_MAX_PAGES
            and mandatory_pages > self.config.PACKAGE_PLAN_MAX_PAGES
        ):
            issues.append("Package page count is outside configured bounds")
        issues.extend(recomputed.unresolved_dependencies)
        if issues:
            raise ValidationError("PackageContentPlan validation failed", payload={"issues": list(dict.fromkeys(issues))})
        return recomputed

    def apply_to_lesson_spec(self, plan: PackageContentPlan, lesson_spec: LessonSpec) -> LessonSpec:
        plan = self.validate(plan, lesson_spec)
        existing = {item.material_type: item for item in lesson_spec.material_requests}
        requests = list(lesson_spec.material_requests)
        for material_type in self.included_material_types(plan):
            if material_type in existing:
                continue
            blueprint = V2MaterialBlueprintService.blueprint(material_type)
            if blueprint is None and material_type not in self.additional_supported_materials:
                raise ValidationError(f"Unsupported planned material: {material_type}")
            reason, factor_ids = self._reason_and_factors(plan, material_type)
            requests.append(LessonSpecMaterialRequest(
                requestId=f"{plan.id}-{material_type}",
                materialType=material_type,
                displayLabel=(blueprint.display_name if blueprint else self.additional_supported_materials[material_type]),
                instructionalPurpose=reason,
                required=True,
                supported=True,
                profileFactorIds=factor_ids or lesson_spec.profile_factor_ids,
                configuration=self._configuration(material_type, lesson_spec),
            ))
        return lesson_spec.model_copy(update={"material_requests": requests})

    def recompute(self, plan: PackageContentPlan) -> PackageContentPlan:
        included = self.included_types(plan)
        pages = sum(self._pages(item) for item in self.included_material_types(plan))
        unresolved: list[str] = []
        for companion in plan.required_companions:
            if not companion.included:
                continue
            missing = [item for item in companion.depends_on_material_types if item not in included]
            if missing:
                unresolved.append(f"{companion.material_type} depends on: {', '.join(missing)}")
        return plan.model_copy(update={
            "estimated_artifact_count": len(included),
            "estimated_page_count": pages,
            "unresolved_dependencies": unresolved,
        })

    def included_types(self, plan: PackageContentPlan) -> set[str]:
        return set(self.included_material_types(plan))

    @staticmethod
    def included_material_types(plan: PackageContentPlan) -> list[str]:
        return list(dict.fromkeys([
            *[item.material_type for item in plan.teacher_selected_core],
            *[item.material_type for item in plan.required_companions if item.included],
            *[item.material_type for item in plan.optional_enrichments if item.default_included],
        ]))

    def _communication_companions(self, spec: LessonSpec, plan: PackageContentPlan) -> None:
        text = self._goal_text(spec)
        if not self._is_communication_goal(text):
            return
        card = "break_card" if "break" in text else "help_card"
        self._require(plan, card, "Provides the exact functional communication response for practice.", "Functional communication response", spec.profile_factor_ids)
        self._require(plan, "teacher_cue_card", "Keeps wait time, prompting, response acceptance, and return instructions visible to the teacher.", "Prompting and response-access fidelity", spec.profile_factor_ids, removable=True)
        self._require(plan, "data_sheet", "Records the response mode, independence, and prompt level for the selected goal.", "Measurable communication goal", spec.profile_factor_ids)
        self._require(plan, "scenario_cards", "Creates distinct opportunities to use the communication response across contexts.", "Communication generalization", spec.profile_factor_ids)
        self._require(
            plan,
            "summary_template",
            "Captures goal-specific outcomes, response modes, support used, and the next generalization step.",
            "Complete post-lesson interpretation",
            spec.profile_factor_ids,
        )

    def _transition_companions(self, spec: LessonSpec, plan: PackageContentPlan) -> None:
        text = self._goal_text(spec)
        if not self._is_transition_goal(spec, text):
            return
        self._require(plan, "first_then_board", "Makes the current transition and next outcome concrete.", "Transition predictability", spec.profile_factor_ids)
        self._require(plan, "teacher_cue_card", "Combines the transition warning, prompting sequence, and return-to-task support.", "Transition warning and return support", spec.profile_factor_ids, removable=True)
        if spec.transition_plan.break_duration_minutes:
            self._require(plan, "visual_timer", "Shows the confirmed timed break without prohibited audio.", "Timed break", spec.profile_factor_ids)
        if spec.transition_plan.break_request:
            self._require(plan, "break_card", "Keeps the confirmed break request available during transitions.", "Break communication access", spec.profile_factor_ids)
        self._require(plan, "scenario_cards", "Provides transition practice across the confirmed contexts.", "Transition generalization", spec.profile_factor_ids)
        self._require(plan, "data_sheet", "Separates transition context, response mode, and independence.", "Transition progress measurement", spec.profile_factor_ids)

    def _token_companions(self, spec: LessonSpec, plan: PackageContentPlan) -> None:
        selected = {item.material_type for item in plan.teacher_selected_core}
        reinforcement = spec.reinforcement_plan
        if "token_board" not in selected and not (reinforcement.token_count and reinforcement.earned_reward):
            return
        self._require(plan, "token_board", "Preserves the confirmed token count, pictured earned reward, praise, and delivery instructions.", "Confirmed token reinforcement system", spec.profile_factor_ids, removable="token_board" not in selected)

    def _activity_companions(self, spec: LessonSpec, plan: PackageContentPlan) -> None:
        selected = {item.material_type for item in plan.teacher_selected_core}
        if "blue_line_activity" in selected:
            return
        context_text = " ".join(
            [self._goal_text(spec), *[item.label.casefold() for item in spec.contexts]]
        )
        theme_terms = {
            term
            for theme in spec.personalization_themes
            for term in theme.casefold().replace("-", " ").split()
            if len(term) >= 4
        }
        relevant_theme = any(
            term in context_text or term.rstrip("s") in context_text
            for term in theme_terms
        )
        if (
            spec.personalization_themes
            and spec.contexts
            and self._is_transition_goal(spec, self._goal_text(spec))
            and relevant_theme
        ):
            self._require(plan, "blue_line_activity", "Adds an executable theme-linked activity with setup, components, answer sequence, and a generalization variation.", "Profile-supported personalized practice", spec.profile_factor_ids, removable=True)

    def _generalization_companions(self, spec: LessonSpec, plan: PackageContentPlan) -> None:
        if not spec.generalization_plan.required:
            return
        self._require(plan, "scenario_cards", "Represents at least three confirmed contexts or exemplars.", "Required generalization across contexts", spec.profile_factor_ids)
        self._require(plan, "data_sheet", "Records performance separately by context and response mode.", "Generalization measurement", spec.profile_factor_ids)

    def _add_contextual_enrichments(self, spec: LessonSpec, plan: PackageContentPlan) -> None:
        text = self._goal_text(spec)
        if self._is_concept_identification_goal(text):
            # A concept lesson needs varied object discrimination and matching,
            # not a one-step task analysis or a duplicate session summary. Keep
            # these teacher-controllable while making the default kit executable.
            candidates = [
                ("teacher_cue_card", "Keeps the concept cue, wait time, response modes, and neutral correction visible."),
            ]
        else:
            candidates = [
                ("teacher_cue_card", "Adds a compact teacher setup, prompting, and correction guide."),
                ("task_analysis_cards", "Adds an executable step sequence when the goal benefits from component teaching."),
                ("summary_template", "Adds a concise post-lesson reflection and next-step record."),
                ("session_summary", "Adds a second teacher-facing session summary for handoff or another setting."),
                ("choice_board", "Offers an additional supported choice-based practice format."),
                ("visual_schedule", "Adds an optional compact sequence for use in another routine or setting."),
            ]
        if self._is_transition_goal(spec, text):
            candidates.insert(0, ("sequence_cards", "Offers a second route or transition-sequencing variation."))
        for material_type, reason in candidates:
            if material_type in self._all_types(plan):
                continue
            current = self.recompute(plan)
            include = (
                current.estimated_artifact_count < self.config.PACKAGE_PLAN_MIN_ARTIFACTS
                or current.estimated_page_count < self.config.PACKAGE_PLAN_MIN_PAGES
            )
            if include and current.estimated_artifact_count + 1 > self.config.PACKAGE_PLAN_MAX_ARTIFACTS:
                include = False
            if include and current.estimated_page_count + self._pages(material_type) > self.config.PACKAGE_PLAN_MAX_PAGES:
                include = False
            plan.optional_enrichments.append(PackageOptionalEnrichment(
                materialType=material_type, reasonSuggested=reason,
                profileFactorIds=spec.profile_factor_ids,
                defaultIncluded=include, estimatedPages=self._pages(material_type),
            ))

    def _rebalance_optionals(self, plan: PackageContentPlan, *, exclude: str = "") -> None:
        """Keep default size targets after a teacher removes one optional item.

        Alternatives are already visible in the preview, so this never adds an
        undisclosed catalog item.
        """

        for item in plan.optional_enrichments:
            current = self.recompute(plan)
            if (
                current.estimated_artifact_count >= self.config.PACKAGE_PLAN_MIN_ARTIFACTS
                and current.estimated_page_count >= self.config.PACKAGE_PLAN_MIN_PAGES
            ):
                return
            if item.material_type == exclude or item.default_included:
                continue
            if current.estimated_artifact_count + 1 > self.config.PACKAGE_PLAN_MAX_ARTIFACTS:
                continue
            if current.estimated_page_count + item.estimated_pages > self.config.PACKAGE_PLAN_MAX_PAGES:
                continue
            item.default_included = True

    def _require(self, plan, material_type, reason, requirement, factors, removable=False) -> None:
        if material_type in {item.material_type for item in plan.teacher_selected_core}:
            return
        existing = next((item for item in plan.required_companions if item.material_type == material_type), None)
        if existing:
            existing.reason_required = f"{existing.reason_required} {reason}"
            return
        if not self._is_supported(material_type):
            plan.unresolved_dependencies.append(f"Required companion is unsupported: {material_type}")
            return
        plan.required_companions.append(PackageRequiredCompanion(
            materialType=material_type, reasonRequired=reason,
            goalRequirement=requirement, profileFactorIds=factors,
            canTeacherRemove=bool(removable),
            removalWarning=(
                "Removing this strongly recommended companion may reduce package completeness; the remaining plan will be revalidated."
                if removable else
                "This companion cannot be removed because the selected goal would become semantically incomplete."
            ),
        ))

    @staticmethod
    def _goal_text(spec: LessonSpec) -> str:
        return " ".join([spec.goal.display_text, spec.goal.observable_behavior, spec.goal.conditions, spec.teacher_request]).casefold()

    @staticmethod
    def _is_communication_goal(text: str) -> bool:
        return any(term in text for term in ("request", "ask for", "communicat", "break, please", "help, please", "aac"))

    @staticmethod
    def _is_transition_goal(spec: LessonSpec, text: str) -> bool:
        return "transition" in text or any(item.transition_from or item.transition_to for item in spec.contexts)

    @staticmethod
    def _is_concept_identification_goal(text: str) -> bool:
        return any(
            term in text
            for term in (
                "identify",
                "identifies",
                "name the",
                "names the",
                "recognize",
                "recognizes",
            )
        )

    @classmethod
    def _is_compact_concept_package(
        cls, spec: LessonSpec, included: set[str]
    ) -> bool:
        text = cls._goal_text(spec)
        required = {"visual_card", "data_sheet"}
        return cls._is_concept_identification_goal(text) and required <= included

    @classmethod
    def _pages(cls, material_type: str) -> int:
        return cls.page_estimates.get(material_type, 1)

    @staticmethod
    def _all_types(plan: PackageContentPlan) -> set[str]:
        return {
            *[item.material_type for item in plan.teacher_selected_core],
            *[item.material_type for item in plan.required_companions],
            *[item.material_type for item in plan.optional_enrichments],
            *[item.material_type for item in plan.excluded_materials],
        }

    @classmethod
    def _is_supported(cls, material_type: str) -> bool:
        return (
            V2MaterialBlueprintService.blueprint(material_type) is not None
            or material_type in cls.additional_supported_materials
        )

    @staticmethod
    def _reason_and_factors(plan, material_type):
        for items, reason_field in ((plan.required_companions, "reason_required"), (plan.optional_enrichments, "reason_suggested")):
            for item in items:
                if item.material_type == material_type:
                    return getattr(item, reason_field), item.profile_factor_ids
        return "Teacher-selected core material.", []

    @staticmethod
    def _configuration(material_type: str, spec: LessonSpec) -> list[LessonMaterialConfigurationEntry]:
        if material_type == "token_board":
            return [
                LessonMaterialConfigurationEntry(key="tokenCount", value=spec.reinforcement_plan.token_count),
                LessonMaterialConfigurationEntry(key="reward", value=spec.reinforcement_plan.earned_reward),
            ]
        if material_type == "blue_line_activity":
            return [
                LessonMaterialConfigurationEntry(
                    key="activityTitle", value="Complete the Blue Line"
                )
            ]
        return []
