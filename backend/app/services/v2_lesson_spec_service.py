from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import ValidationError
from app.schemas.v2_dto import (
    GoalDecisionValue,
    InstructionalConstraintSnapshot,
    LearnerProfile,
    LessonCommunicationPlan,
    LessonDataPlan,
    LessonDurationSpec,
    LessonErrorCorrectionSpec,
    LessonGeneralizationPlan,
    LessonMaterialConfigurationEntry,
    LessonPromptingPlan,
    LessonReinforcementPlan,
    LessonSpec,
    LessonSpecAssumption,
    LessonSpecFieldResolution,
    LessonSpecGoal,
    LessonSpecMaterialRequest,
    LessonSpecProvenance,
    LessonSpecValidationIssue,
    LessonSpecValidationReport,
    LessonSuccessCriterion,
    LessonTransitionPlan,
    LessonAccessPlan,
    LessonDesignDraftDto,
    MaterialRequestDecisionValue,
    PracticeContextDecisionValue,
    PracticeContextItem,
    TeacherDecision,
)


class V2LessonSpecService:
    """Canonical deterministic boundary between planning and generation.

    Application logic owns constraints, provenance, data semantics, selected
    material coverage, identifiers, and validation. Providers receive a valid
    LessonSpec and may author prose only; they never resolve these fields.
    """

    def from_draft(
        self,
        draft: LessonDesignDraftDto,
        learner: LearnerProfile,
        snapshot: InstructionalConstraintSnapshot,
    ) -> LessonSpec:
        decisions = list(draft.decisions) or self._adapt_legacy_decisions(draft, snapshot)
        by_field = {item.field: item for item in decisions}
        resolutions: list[LessonSpecFieldResolution] = []

        def resolved(path: str, source: str, reason: str, confirm: bool = False) -> None:
            resolutions.append(
                LessonSpecFieldResolution(
                    fieldPath=path,
                    source=source,
                    reason=reason,
                    requiresTeacherConfirmation=confirm,
                )
            )

        goal_decision = by_field.get("goal")
        goal_value = (
            goal_decision.value
            if goal_decision and isinstance(goal_decision.value, GoalDecisionValue)
            else GoalDecisionValue(
                teacherRequest=draft.teacherRequest,
                interpretedGoal=draft.goalText,
                observableBehavior=draft.observableResponse or draft.goalText,
                conditions=", ".join(draft.scenarios),
            )
        )
        goal_source = self._decision_source(goal_decision)
        resolved("goal", goal_source, "Confirmed goal decision." if goal_decision else "Adapted from legacy goal fields.")

        context_decision = by_field.get("practice_contexts")
        contexts = (
            list(context_decision.value.contexts)
            if context_decision and isinstance(context_decision.value, PracticeContextDecisionValue)
            else [
                PracticeContextItem(id=f"legacy-context-{index + 1}", label=value, setting=value)
                for index, value in enumerate(draft.scenarios)
            ]
        )
        resolved(
            "contexts",
            self._decision_source(context_decision),
            "Teacher-confirmed practice contexts." if context_decision else "Adapted from legacy scenarios.",
        )

        total_opportunities = max(1, draft.opportunities or 5)
        required_successes = max(1, total_opportunities - 1)
        required_contexts = (
            max(1, len(snapshot.generalization.contexts))
            if snapshot.generalization.required else 1
        )
        success = LessonSuccessCriterion(
            requiredSuccessfulOpportunities=required_successes,
            totalOpportunities=total_opportunities,
            maximumPromptLevel="Independent or the teacher-confirmed maximum prompt level",
            requiredContexts=max(1, required_contexts),
        )
        resolved(
            "goal.successCriterion",
            "explicit_default",
            "Uses a visible four-of-five style criterion derived from planned opportunities; teacher confirmation is required.",
            True,
        )

        accepted_modes = self._unique(
            goal_value.accepted_response_modes
            or snapshot.communication.accepted_modes
            or ([draft.responseLevel] if draft.responseLevel else [])
        )
        resolved(
            "goal.acceptedResponseModes",
            "profile_derived" if snapshot.communication.accepted_modes else "legacy_adapter",
            "Copied from confirmed communication constraints." if snapshot.communication.accepted_modes else "Adapted from the legacy response-level field.",
        )

        total_minutes = self._duration_minutes(draft.duration) or 25
        if self._duration_minutes(draft.duration) is None:
            resolved("duration.totalMinutes", "explicit_default", "No total lesson duration was confirmed; 25 minutes is an editable scheduling default.", True)
        else:
            resolved("duration.totalMinutes", "teacher_selected", "Parsed from the teacher-confirmed duration.")
        maximum_block = snapshot.instruction.activity_duration_minutes or total_minutes
        resolved(
            "duration.maximumActivityBlockMinutes",
            "profile_derived" if snapshot.instruction.activity_duration_minutes else "explicit_default",
            "Confirmed learner activity limit." if snapshot.instruction.activity_duration_minutes else "No learner block limit was available; total duration is used and requires confirmation.",
            snapshot.instruction.activity_duration_minutes is None,
        )

        processing = snapshot.communication.processing_time_seconds
        resolved("communicationPlan.processingTimeSeconds", "profile_derived", "Confirmed processing-time constraint." if processing is not None else "No processing time was confirmed; value remains unresolved.", processing is None)
        response_rules = self._unique([
            *snapshot.communication.access_requirements,
            *([] if not accepted_modes else [f"Accept any confirmed mode equally: {', '.join(accepted_modes)}"]),
        ])

        prompt_sequence = self._unique(snapshot.instruction.prompt_hierarchy)
        if not prompt_sequence and draft.promptingStart.strip():
            prompt_sequence = [item.strip() for item in re.split(r",|\bthen\b", draft.promptingStart) if item.strip()]
            resolved("promptingPlan.sequence", "legacy_adapter", "Adapted from the legacy prompting field.", True)
        else:
            resolved("promptingPlan.sequence", "profile_derived", "Copied from confirmed prompting constraints.")
        wait_time = processing if processing is not None else self._seconds(draft.promptingStart)
        resolved("promptingPlan.waitTimeSeconds", "profile_derived" if processing is not None else "legacy_adapter", "Uses confirmed processing time before prompting." if processing is not None else "Parsed from legacy prompting text.", processing is None)
        resolved("promptingPlan.teacherOverride", "legacy_adapter", "Preserved from the teacher-reviewable draft prompting limits.", True)
        resolved(
            "errorCorrectionPlan",
            "profile_derived" if snapshot.instruction.error_correction else "legacy_adapter",
            "Copied from confirmed error-correction constraints." if snapshot.instruction.error_correction else "Adapted from the legacy teacher-reviewed error-correction field.",
            not bool(snapshot.instruction.error_correction),
        )
        if draft.customNotes or draft.teacherConstraints or draft.structuredChanges:
            resolved("teacherEdits", "teacher_authored", "Preserves explicit teacher notes and structured follow-up edits verbatim.")

        reinforcers = list(snapshot.engagement.effective_reinforcers)
        raw_excluded_reinforcers = [
            *snapshot.engagement.not_approved_reinforcers,
            *snapshot.engagement.not_meaningful_reinforcers,
        ]
        confirmed_token_count = self._first_number(reinforcers, ("token",))
        token_requested = any(
            self._material_type(item) == "token_board"
            for item in draft.selectedMaterials
        )
        token_count = confirmed_token_count or (5 if token_requested else None)
        token_theme = self._token_theme(reinforcers) or (
            snapshot.engagement.current_interests[0]
            if token_requested and snapshot.engagement.current_interests
            else ""
        )
        earned_reward = next(
            (item for item in reinforcers if "token" not in item.casefold() and "praise" not in item.casefold()),
            "",
        )
        if not earned_reward:
            earned_reward = self._reward_after_token_exchange(reinforcers)
        reward_minutes = self._minutes(earned_reward)
        praise = next((item for item in reinforcers if "praise" in item.casefold()), "")
        if not praise:
            praise = self._explicit_acknowledgment(raw_excluded_reinforcers)
        earned_reward = self._concrete_reward_phrase(earned_reward, reward_minutes)
        praise = re.sub(r"^specific\s+praise\s*:\s*", "", praise, flags=re.I).strip()
        resolved(
            "reinforcementPlan.tokenCount",
            "profile_derived" if confirmed_token_count is not None else "explicit_default",
            "Derived only from confirmed reinforcement constraints." if confirmed_token_count is not None else "A five-token working default is explicit and requires teacher confirmation because the selected token board had no confirmed count.",
            confirmed_token_count is None and token_requested,
        )
        for path, value in (
            ("reinforcementPlan.tokenTheme", token_theme),
            ("reinforcementPlan.earnedReward", earned_reward),
            ("reinforcementPlan.rewardDurationMinutes", reward_minutes),
            ("reinforcementPlan.specificPraise", praise),
        ):
            resolved(path, "profile_derived" if value not in (None, "") else "explicit_default", "Derived only from confirmed reinforcement constraints." if value not in (None, "") else "No confirmed value; intentionally left empty.", value in (None, ""))

        warning = next((item for item in snapshot.transitions_and_breaks.transition_warnings if "warning" in item.casefold()), "")
        return_support = next(iter(snapshot.transitions_and_breaks.return_supports), "")
        break_request = next(iter(snapshot.transitions_and_breaks.break_request_options), "")
        resolved("transitionPlan", "profile_derived", "Copied from confirmed transition and break constraints.")
        resolved("accessPlan", "profile_derived", "Copied from confirmed visual, sensory, and motor-access constraints.")

        materials = self._materials(draft, by_field.get("material_requests"), snapshot)
        # A token board without a teacher-confirmed earned reward is not an
        # executable reinforcement system. Do not block the entire lesson kit
        # or invent a reward: retain the request as an explicit exclusion so
        # every other confirmed material can continue to package preview.
        if not earned_reward:
            materials = [
                item.model_copy(
                    update={
                        "required": False,
                        "supported": False,
                        "unsupported_reason": (
                            "Not included because no teacher-confirmed earned "
                            "reward is available for this token board."
                        ),
                    }
                )
                if item.material_type == "token_board"
                else item
                for item in materials
            ]
        resolved("materialRequests", self._decision_source(by_field.get("material_requests")), "Preserves the complete confirmed material-request decision.")

        assumptions = self._assumptions(learner, snapshot)
        measures = self._data_measures(goal_value.observable_behavior or draft.goalText, accepted_modes)
        resolved("dataPlan.measures", "profile_derived", "Deterministically derived from the observable goal and accepted response modes.")

        provenance = self._provenance(decisions, resolutions)
        spec = LessonSpec(
            id=f"lesson-spec-{draft.id}",
            revision=max(1, max((item.revision for item in decisions), default=1)),
            learnerId=draft.learnerId,
            profileRevision=snapshot.profile_revision,
            teacherRequest=draft.teacherRequest or goal_value.teacher_request,
            teacherEdits=self._unique([
                draft.customNotes,
                draft.teacherConstraints,
                *(item.original_message for item in draft.structuredChanges),
            ]),
            goal=LessonSpecGoal(
                displayText=goal_value.interpreted_goal or draft.goalText,
                observableBehavior=goal_value.observable_behavior or draft.observableResponse or draft.goalText,
                conditions=goal_value.conditions or ", ".join(item.label for item in contexts),
                acceptedResponseModes=accepted_modes,
                independenceDefinition="The target response occurs without a teacher prompt after the natural cue and confirmed processing time.",
                successCriterion=success,
            ),
            duration=LessonDurationSpec(totalMinutes=total_minutes, maximumActivityBlockMinutes=maximum_block),
            contexts=contexts,
            communicationPlan=LessonCommunicationPlan(
                acceptedModes=accepted_modes,
                processingTimeSeconds=processing,
                responseValidationRules=response_rules,
            ),
            promptingPlan=LessonPromptingPlan(
                sequence=prompt_sequence,
                prohibitedPrompts=snapshot.instruction.prohibited_prompting,
                fadeRule="Fade to the least intrusive support after successful responding; teacher may pause or stop.",
                waitTimeSeconds=wait_time,
                teacherOverride=draft.promptingLimits,
            ),
            errorCorrectionPlan=LessonErrorCorrectionSpec(
                strategies=(
                    snapshot.instruction.error_correction
                    or ([draft.errorCorrection] if draft.errorCorrection.strip() else [])
                )
            ),
            reinforcementPlan=LessonReinforcementPlan(
                tokenCount=token_count,
                tokenTheme=token_theme,
                earnedReward=earned_reward,
                rewardDurationMinutes=reward_minutes,
                specificPraise=praise,
                excludedReinforcers=self._unique(
                    [
                        self._excluded_reinforcer_clause(item)
                        for item in raw_excluded_reinforcers
                    ]
                ),
            ),
            transitionPlan=LessonTransitionPlan(
                warning=warning,
                firstThenRequired=snapshot.transitions_and_breaks.first_then_required,
                breakRequest=break_request,
                breakDurationMinutes=snapshot.transitions_and_breaks.break_duration_minutes,
                returnSupport=return_support,
            ),
            accessPlan=LessonAccessPlan(
                maximumPrimaryVisualChoices=snapshot.visual_and_sensory_access.maximum_primary_choices,
                layoutRequirements=snapshot.visual_and_sensory_access.layout_requirements,
                prohibitedVisualFeatures=snapshot.visual_and_sensory_access.prohibited_visual_features,
                prohibitedAudioFeatures=snapshot.visual_and_sensory_access.prohibited_audio_features,
                motorAccessAlternatives=snapshot.visual_and_sensory_access.motor_access_alternatives,
            ),
            generalizationPlan=LessonGeneralizationPlan(
                required=snapshot.generalization.required,
                contexts=contexts,
                dimensions=self._unique([item.generalization_dimension for item in contexts]),
            ),
            dataPlan=LessonDataPlan(
                measures=measures,
                trialDefinition="One naturally cued opportunity in a selected context, ending with the learner response, a break/stop decision, or the planned trial timeout.",
                independenceDefinition="No teacher prompt after the natural cue and confirmed processing interval.",
                promptLevels=["independent", *prompt_sequence],
            ),
            materialRequests=materials,
            safetyConstraints=snapshot.safety_constraints,
            personalizationThemes=snapshot.engagement.current_interests,
            unresolvedAssumptions=assumptions,
            profileFactorIds=snapshot.profile_factor_ids,
            decisionIds=[item.id for item in decisions],
            provenance=provenance,
        )
        return spec

    def validate(
        self,
        spec: LessonSpec,
        snapshot: InstructionalConstraintSnapshot,
    ) -> LessonSpecValidationReport:
        issues: list[LessonSpecValidationIssue] = []

        def issue(path: str, code: str, message: str, remediation: str) -> None:
            issues.append(LessonSpecValidationIssue(fieldPath=path, code=code, message=message, remediation=remediation))

        if spec.profile_revision != snapshot.profile_revision:
            issue("profileRevision", "stale_profile_revision", "LessonSpec uses an outdated learner-profile revision.", "Refresh recommendations and rebuild the LessonSpec from the current profile.")
        if not spec.decision_ids:
            issue("decisionIds", "missing_teacher_decisions", "No confirmed teacher decisions are attached.", "Confirm the goal, contexts, and materials before generation.")
        if not spec.goal.observable_behavior.strip():
            issue("goal.observableBehavior", "missing_observable_behavior", "Observable behavior is required.", "Write a visible or measurable learner action.")
        criterion = spec.goal.success_criterion
        if criterion is None or criterion.required_successful_opportunities is None or criterion.total_opportunities is None:
            issue("goal.successCriterion", "missing_success_criterion", "A complete success criterion is required.", "Confirm successful opportunities, total opportunities, prompt limit, and required contexts.")
        elif criterion.required_successful_opportunities > criterion.total_opportunities:
            issue("goal.successCriterion.requiredSuccessfulOpportunities", "contradictory_success_criterion", "Required successes exceed total opportunities.", "Reduce required successes or increase total opportunities.")

        confirmed_modes = {self._norm(item) for item in snapshot.communication.accepted_modes}
        unsupported_modes = [item for item in spec.goal.accepted_response_modes if confirmed_modes and self._norm(item) not in confirmed_modes]
        if unsupported_modes:
            issue("goal.acceptedResponseModes", "unsupported_response_method", f"Unsupported response modes: {', '.join(unsupported_modes)}.", "Choose only profile-confirmed response modes or update the learner profile.")
        if {self._norm(item) for item in spec.goal.accepted_response_modes} != {self._norm(item) for item in spec.communication_plan.accepted_modes}:
            issue("communicationPlan.acceptedModes", "contradictory_response_modes", "Goal and communication-plan response modes disagree.", "Use one identical confirmed response-mode set.")

        prohibited_prompts = snapshot.instruction.prohibited_prompting
        bad_prompts = [prompt for prompt in spec.prompting_plan.sequence if any(self._contains_equivalent(prompt, prohibited) for prohibited in prohibited_prompts)]
        if bad_prompts:
            issue("promptingPlan.sequence", "prohibited_prompting", f"Prompting sequence includes prohibited support: {', '.join(bad_prompts)}.", "Remove the prohibited prompt and choose a confirmed alternative.")
        if (
            spec.prompting_plan.wait_time_seconds is not None
            and spec.communication_plan.processing_time_seconds is not None
            and spec.prompting_plan.wait_time_seconds != spec.communication_plan.processing_time_seconds
        ):
            issue("promptingPlan.waitTimeSeconds", "contradictory_wait_time", "Prompt wait time disagrees with the communication processing time.", "Use the confirmed processing interval in both fields.")

        selected_reinforcement = [spec.reinforcement_plan.earned_reward, spec.reinforcement_plan.specific_praise]
        excluded = spec.reinforcement_plan.excluded_reinforcers
        prohibited = [value for value in selected_reinforcement if value and any(self._contains_equivalent(value, item) for item in excluded)]
        if prohibited:
            issue("reinforcementPlan", "prohibited_reinforcer", f"Selected reinforcement is excluded: {', '.join(prohibited)}.", "Select a confirmed effective reinforcer that is not excluded.")

        limit = snapshot.instruction.activity_duration_minutes
        if limit is not None and spec.duration.maximum_activity_block_minutes > limit:
            issue("duration.maximumActivityBlockMinutes", "activity_limit_exceeded", f"Activity block exceeds the confirmed {limit}-minute limit.", "Split the lesson into shorter activity blocks.")
        if spec.generalization_plan.required and criterion is not None and len(spec.contexts) < criterion.required_contexts:
            issue("contexts", "insufficient_generalization_contexts", "Required generalization does not have enough selected contexts.", f"Select at least {criterion.required_contexts} contexts.")
        for index, material in enumerate(spec.material_requests):
            if not material.instructional_purpose.strip():
                issue(f"materialRequests.{index}.instructionalPurpose", "missing_material_purpose", "Material request has no instructional purpose.", "Describe how this artifact supports the goal.")
            if material.required and not material.supported:
                issue(f"materialRequests.{index}.supported", "unsupported_required_material", "A required material is unsupported.", "Select a supported equivalent or save it as a non-required future request.")
        for index, assumption in enumerate(spec.unresolved_assumptions):
            if assumption.blocking:
                issue(f"unresolvedAssumptions.{index}", "blocking_assumption", assumption.text, "Resolve this assumption in the learner profile before generation.")
        return LessonSpecValidationReport(valid=not issues, issues=issues)

    def require_valid(self, spec: LessonSpec, snapshot: InstructionalConstraintSnapshot) -> LessonSpec:
        report = self.validate(spec, snapshot)
        if not report.valid:
            raise ValidationError(
                "LessonSpec validation failed",
                payload={"lessonSpecId": spec.id, **report.model_dump(mode="json", by_alias=True)},
            )
        return spec

    def _adapt_legacy_decisions(self, draft: LessonDesignDraftDto, snapshot: InstructionalConstraintSnapshot) -> list[TeacherDecision]:
        contexts = [PracticeContextItem(id=f"legacy-context-{i+1}", label=value, setting=value) for i, value in enumerate(draft.scenarios)]
        materials = [
            self._legacy_material(item, snapshot) for item in draft.selectedMaterials
        ]
        return [
            TeacherDecision(
                id=f"legacy-decision-{draft.id}-goal", field="goal", source="teacher_authored",
                value=GoalDecisionValue(
                    teacherRequest=draft.teacherRequest or draft.goalText,
                    interpretedGoal=draft.goalText,
                    observableBehavior=draft.observableResponse or draft.goalText,
                    conditions=", ".join(draft.scenarios),
                    acceptedResponseModes=snapshot.communication.accepted_modes or ([draft.responseLevel] if draft.responseLevel else []),
                ),
                affects=["lesson", "teaching_flow", "materials", "data_sheet"],
                reason="Compatibility adapter preserved the legacy goal verbatim.",
            ),
            TeacherDecision(
                id=f"legacy-decision-{draft.id}-contexts", field="practice_contexts", source="teacher_selected",
                value=PracticeContextDecisionValue(contexts=contexts), optionIds=[item.id for item in contexts],
                affects=["teaching_flow", "generalization_plan", "scenario_cards"],
                reason="Compatibility adapter preserved legacy scenarios.",
            ),
            TeacherDecision(
                id=f"legacy-decision-{draft.id}-materials", field="material_requests", source="teacher_selected",
                value=MaterialRequestDecisionValue(materials=materials), optionIds=[item.request_id for item in materials],
                affects=["materials", "printable_package"],
                reason="Compatibility adapter preserved legacy material selections.",
            ),
        ]

    def _materials(self, draft: LessonDesignDraftDto, decision: TeacherDecision | None, snapshot: InstructionalConstraintSnapshot) -> list[LessonSpecMaterialRequest]:
        requests = (
            decision.value.materials
            if decision and isinstance(decision.value, MaterialRequestDecisionValue)
            else [self._legacy_material(item, snapshot) for item in draft.selectedMaterials]
        )
        result: list[LessonSpecMaterialRequest] = []
        for item in requests:
            config = [
                LessonMaterialConfigurationEntry(key=str(key), value=self._scalar(value))
                for key, value in sorted((item.library_configuration or {}).items())
            ]
            result.append(LessonSpecMaterialRequest(
                requestId=item.request_id,
                materialType=self._material_type(item.material_type),
                displayLabel=item.custom_label or item.material_type.replace("_", " ").title(),
                instructionalPurpose=item.purpose,
                required=item.required,
                supported=item.supported,
                unsupportedReason=item.unsupported_reason,
                profileFactorIds=item.profile_factor_ids,
                origin=item.origin,
                libraryMaterialId=item.library_material_id,
                libraryMaterialVersion=item.library_material_version,
                configuration=config,
            ))
        return result

    def _legacy_material(self, value: str, snapshot: InstructionalConstraintSnapshot):
        from app.schemas.v2_dto import MaterialRequestItem
        return MaterialRequestItem(
            requestId=f"legacy-material-{re.sub(r'[^a-z0-9]+', '-', value.casefold()).strip('-')}",
            materialType=self._material_type(value),
            customLabel=value,
            purpose=f"Legacy teacher selection supporting the goal: {value}.",
            profileFactorIds=snapshot.profile_factor_ids,
        )

    @staticmethod
    def _material_type(value: str) -> str:
        normalized = " ".join(value.replace("_", " ").replace("-", " ").casefold().split())
        aliases = {
            "visual cards": "visual_card", "visual card": "visual_card",
            "visual_cards": "visual_card",
            "help card": "help_card", "break card": "break_card",
            "token board": "token_board", "reinforcement board": "token_board",
            "reinforcement_board": "token_board",
            "data sheet": "data_sheet", "summary template": "summary_template",
            "lesson summary": "summary_template", "first then board": "first_then_board",
            "scenario cards": "scenario_cards", "choice board": "choice_board",
            "matching practice": "matching_page", "matching_practice": "matching_page",
            "sorting practice": "sorting_page", "sorting_practice": "sorting_page",
            "quantity card": "quantity_cards", "number card": "number_cards",
            "core word communication board": "core_word_board",
            "social situation guide": "social_narrative",
            "emotion regulation scale": "emotion_scale",
            "ipad token board app": "token_board",
        }
        if normalized in aliases:
            return aliases[normalized]
        if normalized.startswith("number cards "):
            return "number_cards"
        if "token board" in normalized:
            return "token_board"
        return normalized.replace(" ", "_")

    @staticmethod
    def _decision_source(decision: TeacherDecision | None) -> str:
        if decision is None:
            return "legacy_adapter"
        return {
            "teacher_authored": "teacher_authored",
            "teacher_edited": "teacher_authored",
            "teacher_selected": "teacher_selected",
            "ai_recommended": "ai_recommended",
        }[decision.source]

    @staticmethod
    def _provenance(decisions: list[TeacherDecision], resolutions: list[LessonSpecFieldResolution]) -> LessonSpecProvenance:
        sources = {item.field: item.source for item in decisions}
        return LessonSpecProvenance(
            teacherAuthoredFields=[field for field, source in sources.items() if source in {"teacher_authored", "teacher_edited"}],
            teacherSelectedFields=[field for field, source in sources.items() if source == "teacher_selected"],
            aiRecommendedFields=[field for field, source in sources.items() if source == "ai_recommended"],
            derivedFields=[item.field_path for item in resolutions if item.source == "profile_derived"],
            defaultedFields=[item.field_path for item in resolutions if item.source == "explicit_default"],
            fieldResolutions=resolutions,
        )

    @staticmethod
    def _assumptions(learner: LearnerProfile, snapshot: InstructionalConstraintSnapshot) -> list[LessonSpecAssumption]:
        factors = learner.normalized_profile.factors if learner.normalized_profile else []
        blocking = set(learner.normalized_profile.blocking_issues if learner.normalized_profile else [])
        result = []
        for text in snapshot.unresolved_assumptions:
            factor = next((item for item in factors if item.value == text and item.category == "unresolved_assumption"), None)
            result.append(LessonSpecAssumption(
                text=text,
                blocking=text in blocking or (factor.id in blocking if factor else False),
                profileFactorId=factor.id if factor else None,
            ))
        return result

    @staticmethod
    def _data_measures(goal: str, modes: list[str]) -> list[str]:
        measures = ["opportunity", "context", "response_outcome", "independence", "prompt_level", "latency_seconds"]
        if len(modes) > 1:
            measures.append("response_mode")
        if "break" in goal.casefold():
            measures.extend(["break_requested", "break_honored", "break_duration_minutes", "returned_to_activity"])
        measures.append("notes")
        return measures

    @staticmethod
    def _duration_minutes(value: str) -> int | None:
        values = [int(item) for item in re.findall(r"\d+", value or "")]
        return max(values) if values else None

    @staticmethod
    def _seconds(value: str) -> int | None:
        match = re.search(r"(\d+)\s*(?:second|sec)", value or "", re.I)
        return int(match.group(1)) if match else None

    @staticmethod
    def _minutes(value: str) -> int | None:
        match = re.search(r"(\d+|one|two|three|four|five)\s*(?:-|\s)?minute", value or "", re.I)
        if not match:
            return None
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        return words.get(match.group(1).casefold(), int(match.group(1)) if match.group(1).isdigit() else None)

    @classmethod
    def _first_number(cls, values: list[str], required_terms: tuple[str, ...]) -> int | None:
        for value in values:
            if all(term in value.casefold() for term in required_terms):
                if required_terms == ("token",):
                    # Only a number attached to the token phrase is a token
                    # count. In "bus tokens exchanged for two minutes", two
                    # is the reward duration and must not become two tokens.
                    match = re.search(
                        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
                        r"(?:[-\s]+[a-z][a-z-]*){0,2}[-\s]+tokens?\b",
                        value,
                        re.I,
                    )
                else:
                    match = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", value, re.I)
                if match:
                    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
                    return int(match.group(1)) if match.group(1).isdigit() else words[match.group(1).casefold()]
        return None

    @staticmethod
    def _token_theme(values: list[str]) -> str:
        for value in values:
            match = re.search(r"with\s+([a-z]+)[- ]icon\s+tokens?", value, re.I)
            if not match:
                match = re.search(r"([a-z]+)[- ]icon\s+tokens?", value, re.I)
            if not match:
                match = re.search(
                    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
                    r"([a-z][a-z-]*)\s+tokens?\b",
                    value,
                    re.I,
                )
            if not match:
                match = re.search(r"\b([a-z][a-z-]*)\s+tokens?\b", value, re.I)
            if match:
                candidate = match.group(1).casefold()
                if candidate not in {
                    "one", "two", "three", "four", "five", "six", "seven",
                    "eight", "nine", "ten",
                }:
                    return candidate
        return ""

    @staticmethod
    def _reward_after_token_exchange(values: list[str]) -> str:
        """Preserve a reward stated in the same sentence as token delivery."""

        for value in values:
            match = re.search(
                r"\btokens?\b.*?\b(?:exchanged?|traded?|redeemed?)\s+for\s+(.+)$",
                value,
                re.I,
            )
            if match:
                return match.group(1).strip(" .;,")
        return ""

    @staticmethod
    def _concrete_reward_phrase(value: str, minutes: int | None) -> str:
        """Turn confirmed shorthand into concrete display language."""

        if not value or minutes is None:
            return value
        normalized = value.casefold()
        if "transit" in normalized and "map" in normalized:
            return f"{minutes} minutes with the transit-route map"
        already_concrete = re.match(
            r"^(?:\d+|one|two|three|four|five)\s+minutes?\s+with\s+(.+)$",
            value,
            re.I,
        )
        if already_concrete:
            return f"{minutes} minutes with {already_concrete.group(1).strip()}"
        subject = re.sub(
            r"^(?:\d+|one|two|three|four|five)[- ]minutes?\s+", "", value,
            flags=re.I,
        )
        subject = re.sub(r"\s+reward$", "", subject, flags=re.I).strip()
        return f"{minutes} minutes with {subject}" if subject else value

    @staticmethod
    def _explicit_acknowledgment(values: list[str]) -> str:
        """Preserve an explicitly approved acknowledgment embedded in a limit.

        Profiles sometimes say, for example, "Food rewards are not approved;
        use specific verbal acknowledgment only." The first clause is an
        exclusion while the second is a confirmed support, not an invented
        reward.
        """

        for value in values:
            match = re.search(
                r"\buse\s+(.+?)(?:\s+only)?(?:[.;]|$)", value, re.I
            )
            if not match:
                continue
            support = re.sub(
                r"\s+only$", "", match.group(1).strip(" .;:"), flags=re.I
            )
            if any(
                term in support.casefold()
                for term in ("acknowledgment", "acknowledgement", "praise")
            ):
                return support
        return ""

    @staticmethod
    def _excluded_reinforcer_clause(value: str) -> str:
        """Keep the prohibited clause separate from any approved alternative."""

        return value.split(";", 1)[0].strip()

    @staticmethod
    def _scalar(value: Any) -> str | int | float | bool | None:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _unique(values):
        return list(dict.fromkeys(item for item in values if item not in (None, "")))

    @staticmethod
    def _norm(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())

    @classmethod
    def _contains_equivalent(cls, left: str, right: str) -> bool:
        a, b = cls._norm(left), cls._norm(right)
        return bool(a and b and (a in b or b in a))
