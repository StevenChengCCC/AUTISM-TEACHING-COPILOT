from __future__ import annotations

import json
import re
from collections.abc import Callable

from app.core.config import Settings, settings
from app.core.exceptions import ValidationError
from app.schemas.v2_dto import (
    ChoiceBoardChoice,
    ChoiceBoardContent,
    ChoiceBoardSpec,
    CommunicationCardContent,
    CommunicationCardSpec,
    FirstThenBoardContent,
    FirstThenBoardSpec,
    GeneratedMaterialDto,
    GoalSpecificDataSheetContent,
    GoalSpecificDataSheetSpec,
    LessonSpec,
    LessonSpecMaterialRequest,
    LessonSummaryContent,
    LessonSummarySpec,
    MaterialApproval,
    MaterialDesignConstraints,
    MaterialSafetyValidationResult,
    MaterialSpec,
    MaterialVisualAssetRequest,
    MaterialValidationIssue,
    MaterialValidationResult,
    PersonalizedInstructionalActivityContent,
    PersonalizedInstructionalActivitySpec,
    RegulationScaleContent,
    RegulationScaleLevel,
    RegulationScaleSpec,
    ScenarioCardItem,
    ScenarioCardsContent,
    ScenarioCardsSpec,
    StructuredSafetyIssue,
    TokenBoardContent,
    TokenBoardSpec,
    VisualTimerContent,
    VisualTimerSpec,
)


class V2MaterialSpecService:
    """Build and validate versioned semantic artifacts from LessonSpec only."""

    supported_material_types = {
        "blue_line_activity",
        "help_card",
        "break_card",
        "first_then_board",
        "token_board",
        "visual_timer",
        "scenario_cards",
        "choice_board",
        "emotion_scale",
        "data_sheet",
        "session_summary",
        "summary_template",
        "teacher_cue_card",
    }
    placeholder_phrases = (
        "practice the target skill",
        "teacher-confirmed reward",
        "teacher-confirmed choice",
        "familiar classroom activity",
        "specific praise",
        "selected reinforcer",
        "add appropriate image",
        "example item",
        "to be confirmed",
    )
    validator_registry = {
        "personalized_instructional_activity": "_validate_personalized_activity",
        "communication_card": "_validate_communication_card",
        "first_then_board": "_validate_first_then_board",
        "token_board": "_validate_token_board",
        "visual_timer": "_validate_visual_timer",
        "scenario_cards": "_validate_scenario_cards",
        "choice_board": "_validate_choice_board",
        "regulation_scale": "_validate_regulation_scale",
        "goal_specific_data_sheet": "_validate_data_sheet",
        "lesson_summary": "_validate_lesson_summary",
    }

    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    @staticmethod
    def render_projection(material_spec: MaterialSpec, existing: dict | None = None) -> dict:
        """Create the schema-v0 renderer bridge from validated typed semantics.

        Provider-authored semantic fields are intentionally discarded so a
        placeholder cannot remain visible after the typed contract has passed.
        Presentation-only choices remain compatible with the current renderer.
        """

        existing = existing or {}
        projected = {
            key: existing[key]
            for key in ("designVariants", "selectedDesignVariant", "artwork", "teacherNote")
            if key in existing
        }
        typed = material_spec.content.model_dump(mode="json", by_alias=True)
        projected.update(typed)
        artifact = material_spec.artifact_type
        if artifact == "personalized_instructional_activity":
            projected.update({
                "instruction": typed["learnerAction"],
                "examples": typed["answerKeyOrExpectedSequence"],
            })
        elif artifact == "communication_card":
            projected.update({
                "phrase": typed["exactCommunicationPhrase"],
                "instruction": typed["cardPurpose"],
            })
        elif artifact == "first_then_board":
            projected.update({
                "firstText": typed["firstTask"],
                "thenText": typed["thenOutcome"],
                "instruction": typed["exactDisplayText"],
            })
        elif artifact == "token_board":
            projected.update({
                "tokens": typed["exactTokenCount"],
                "tokenCount": typed["exactTokenCount"],
                "reward": typed["earnedReward"],
                "instruction": typed["deliveryInstructions"],
            })
        elif artifact == "visual_timer":
            projected.update({
                "instruction": typed["teacherInstruction"],
                "duration": typed["durationMinutes"],
            })
        elif artifact == "scenario_cards":
            projected.update({
                "examples": [item["context"] for item in typed["scenarios"]],
                "instruction": typed["scenarios"][0]["learnerOpportunity"],
            })
        elif artifact == "choice_board":
            projected.update({
                "options": [item["label"] for item in typed["choices"]],
                "instruction": typed["promptOrQuestion"],
            })
        elif artifact == "regulation_scale":
            projected.update({
                "items": [item["label"] for item in typed["levels"]],
                "instruction": typed["nonjudgmentalLanguage"],
            })
        elif artifact == "goal_specific_data_sheet":
            projected.update({
                "columns": typed["exactColumns"],
                "instruction": typed["operationalizedTargetBehavior"],
            })
        elif artifact == "lesson_summary":
            projected.update({
                "prompts": typed["reportingFields"],
                "instruction": typed["observableTarget"],
            })
        return projected

    def adapt_legacy(
        self, material: GeneratedMaterialDto, lesson_spec: LessonSpec
    ) -> GeneratedMaterialDto:
        """Upgrade a historical schema-v0 dictionary payload when supported.

        Historical content is treated only as a compatibility signal. The
        canonical schema-v1 semantics are rebuilt from LessonSpec rather than
        trusting unrestricted dictionary values.
        """

        if material.materialSchemaVersion == 1 and material.materialSpec:
            return material
        material_spec = self.build(
            material_id=material.id,
            package_id=material.packageId,
            material_type=material.type,
            title=material.title,
            lesson_spec=lesson_spec,
        )
        if material_spec is None:
            return material
        return material.model_copy(
            update={"materialSchemaVersion": 1, "materialSpec": material_spec}
        )

    def build(
        self,
        *,
        material_id: str,
        package_id: str,
        material_type: str,
        title: str,
        lesson_spec: LessonSpec,
        visual_asset_requests: list[MaterialVisualAssetRequest] | None = None,
        repair: Callable[[MaterialSpec, list[MaterialValidationIssue], LessonSpec], MaterialSpec] | None = None,
    ) -> MaterialSpec | None:
        request = next(
            (item for item in lesson_spec.material_requests if item.material_type == material_type),
            None,
        )
        if request is None or material_type not in self.supported_material_types:
            return None

        configuration = {
            item.key: item.value for item in request.configuration
        }
        if material_type == "blue_line_activity":
            configured_title = str(configuration.get("activityTitle") or "").strip()
            match = re.match(r"personalized\s+(.+?)\s+activity$", title, re.I)
            title = configured_title or (f"Complete the {match.group(1)}" if match else title)

        common = self._common(
            material_id, package_id, title, request, lesson_spec, material_type,
            visual_asset_requests or [],
        )
        contexts = lesson_spec.contexts
        first_context = contexts[0] if contexts else None
        criterion = lesson_spec.goal.success_criterion
        total = criterion.total_opportunities if criterion and criterion.total_opportunities else 1
        required = criterion.required_successful_opportunities if criterion and criterion.required_successful_opportunities else 1
        response_modes = lesson_spec.goal.accepted_response_modes
        reward = lesson_spec.reinforcement_plan.earned_reward
        prompt_sequence = lesson_spec.prompting_plan.sequence

        if material_type == "blue_line_activity":
            spec: MaterialSpec = PersonalizedInstructionalActivitySpec(
                **common,
                artifactType="personalized_instructional_activity",
                content=PersonalizedInstructionalActivityContent(
                    taskName=title,
                    instructionalObjective=lesson_spec.goal.display_text,
                    learnerAction=(
                        f"Place, point to, or order the {len(contexts)} station cards along the route; "
                        f"at each transition opportunity, {lesson_spec.goal.observable_behavior[:1].casefold() + lesson_spec.goal.observable_behavior[1:]}."
                    ),
                    teacherSetup=[
                        "Place the route page on a stable surface.",
                        "Place the three station cards beside the route within easy reach.",
                        "Model placing or pointing to one station, then reset for the learner.",
                    ],
                    requiredComponents=[
                        "one blue route", "one start marker", "one finish marker",
                        *[f"station card: {item.label}" for item in contexts],
                    ],
                    responseMethod=response_modes,
                    numberOfTrialsOrItems=total,
                    completionCriterion=f"{required} successful opportunities out of {total}",
                    answerKeyOrExpectedSequence=[item.label for item in contexts],
                    generalizationExtension=(
                        "Repeat in the remaining selected contexts: "
                        + "; ".join(item.label for item in contexts[1:])
                        if len(contexts) > 1
                        else "Repeat with another teacher-confirmed person, setting, or material."
                    ),
                    motorAccessRequirements=lesson_spec.access_plan.motor_access_alternatives,
                    visualAccessRequirements=lesson_spec.access_plan.layout_requirements,
                ),
            )
        elif material_type in {"help_card", "break_card"}:
            phrase = self._communication_phrase(lesson_spec, material_type)
            if not phrase or not response_modes:
                return None
            spec = CommunicationCardSpec(
                **common,
                artifactType="communication_card",
                content=CommunicationCardContent(
                    exactCommunicationPhrase=phrase,
                    acceptedCommunicationModes=response_modes,
                    cardPurpose=request.instructional_purpose,
                    symbolDescription=f"One clear symbol representing: {phrase}",
                    alternateText=f"Communication card reading {phrase}",
                    touchTargetRequirement="One large isolated touch target that meets the confirmed motor-access plan",
                    teacherResponseAfterUse=(
                        str(configuration.get("teacherAction") or "").strip()
                        or (
                            f"Honor the request when feasible and begin the {lesson_spec.transition_plan.break_duration_minutes}-minute visual timer."
                            if material_type == "break_card" and lesson_spec.transition_plan.break_duration_minutes
                            else "Acknowledge and honor the communication using the confirmed lesson plan."
                        )
                    ),
                    prohibitedImagery=list(dict.fromkeys([
                        *lesson_spec.access_plan.prohibited_visual_features,
                        "angry or exaggerated faces",
                        "decorative learner photographs",
                    ])),
                ),
            )
        elif material_type == "first_then_board":
            first_task = (
                str(configuration.get("firstTask") or "").strip()
                or first_context.transition_to
                if first_context and first_context.transition_to
                else first_context.label if first_context else lesson_spec.goal.conditions
            )
            then_outcome = str(configuration.get("thenOutcome") or "").strip() or reward or lesson_spec.transition_plan.return_support
            if not first_task or not then_outcome:
                return None
            spec = FirstThenBoardSpec(
                **common,
                artifactType="first_then_board",
                content=FirstThenBoardContent(
                    firstTask=first_task,
                    thenOutcome=then_outcome,
                    exactDisplayText=f"FIRST {first_task} — THEN {then_outcome}",
                    firstSymbolDescription=f"Concrete symbol for {first_task}",
                    thenSymbolDescription=f"Concrete symbol for {then_outcome}",
                    completionCriterion=(
                        str(configuration.get("completionCriterion") or "").strip()
                        or f"Complete the FIRST task as displayed before the THEN outcome begins."
                    ),
                    context=first_context.label if first_context else lesson_spec.goal.conditions,
                    returnOrTransitionInstruction=(
                        str(configuration.get("returnSupport") or "").strip()
                        or lesson_spec.transition_plan.return_support
                        or "Follow the teacher-confirmed transition plan."
                    ),
                ),
            )
        elif material_type == "token_board":
            if not all((lesson_spec.reinforcement_plan.token_count, lesson_spec.reinforcement_plan.token_theme, reward, lesson_spec.reinforcement_plan.specific_praise)):
                return None
            spec = TokenBoardSpec(
                **common,
                artifactType="token_board",
                content=TokenBoardContent(
                    exactTokenCount=lesson_spec.reinforcement_plan.token_count,
                    tokenSymbolOrTheme=lesson_spec.reinforcement_plan.token_theme,
                    earnedReward=reward,
                    rewardDurationMinutes=lesson_spec.reinforcement_plan.reward_duration_minutes,
                    picturedRewardDescription=f"Concrete picture of {reward}",
                    specificPraise=lesson_spec.reinforcement_plan.specific_praise,
                    deliveryInstructions="Deliver one token after the confirmed target response; provide the earned reward after the final token.",
                    prohibitedRewardSubstitutions=lesson_spec.reinforcement_plan.excluded_reinforcers,
                ),
            )
        elif material_type == "visual_timer":
            if not all((lesson_spec.transition_plan.break_duration_minutes, lesson_spec.transition_plan.break_request, lesson_spec.transition_plan.return_support)):
                return None
            spec = VisualTimerSpec(
                **common,
                artifactType="visual_timer",
                content=VisualTimerContent(
                    durationMinutes=lesson_spec.transition_plan.break_duration_minutes,
                    startLabel="Break starts",
                    endLabel="Break finished",
                    displayFormat="Visible countdown without sound",
                    teacherInstruction=lesson_spec.transition_plan.break_request,
                    audioAllowed=not bool(lesson_spec.access_plan.prohibited_audio_features),
                    returnToTaskCue=(
                        str(configuration.get("returnCue") or "").strip()
                        or (
                            "Break finished — check First–Then"
                            if lesson_spec.transition_plan.first_then_required
                            else lesson_spec.transition_plan.return_support
                        )
                    ),
                ),
            )
        elif material_type == "scenario_cards":
            if not contexts or not response_modes:
                return None
            spec = ScenarioCardsSpec(
                **common,
                artifactType="scenario_cards",
                content=ScenarioCardsContent(
                    scenarios=[
                        ScenarioCardItem(
                            id=item.id,
                            context=item.label,
                            triggerOrTransition=(
                                f"{item.transition_from} to {item.transition_to}"
                                if item.transition_from and item.transition_to else item.setting
                            ),
                            learnerOpportunity=lesson_spec.goal.conditions or item.label,
                            expectedResponse=lesson_spec.goal.observable_behavior,
                            acceptedModalities=response_modes,
                            promptSequence=self._prompt_sequence_steps(prompt_sequence),
                            consequenceOrReinforcement=reward or lesson_spec.reinforcement_plan.specific_praise,
                            generalizationDimension=item.generalization_dimension,
                    visualCue=(
                        f"Show the First–Then board for {item.label} and keep the break card available."
                        if lesson_spec.transition_plan.first_then_required
                        else f"Show the primary visual support for {item.label}."
                    ),
                    teacherWording=(
                        f"{item.transition_to or item.setting} is next. You can say or select Break, please."
                        if lesson_spec.transition_plan.break_request
                        else f"Present the opportunity: {lesson_spec.goal.observable_behavior}"
                    ),
                            waitTimeSeconds=lesson_spec.prompting_plan.wait_time_seconds or 5,
                            breakOutcome=(
                                f"Honor the request and begin the {lesson_spec.transition_plan.break_duration_minutes}-minute visual timer."
                                if lesson_spec.transition_plan.break_duration_minutes
                        else lesson_spec.transition_plan.break_request
                        or "Acknowledge the response and continue the planned activity."
                            ),
                            returnSupport=(
                                "Break finished — check First–Then"
                                if lesson_spec.transition_plan.first_then_required
                        else lesson_spec.transition_plan.return_support
                        or "Use the next planned visual or verbal cue to continue."
                            ),
                            generalizationLabel=f"Generalization: {item.generalization_dimension}",
                        )
                        for item in contexts
                    ]
                ),
            )
        elif material_type == "choice_board":
            configured_choices = self._configured_choices(request)
            if len(configured_choices) < 2 or not response_modes:
                return None
            spec = ChoiceBoardSpec(
                **common,
                artifactType="choice_board",
                content=ChoiceBoardContent(
                    promptOrQuestion=lesson_spec.goal.conditions or lesson_spec.goal.display_text,
                    choices=[ChoiceBoardChoice(
                        id=f"choice-{index + 1}", label=label,
                        visualDescription=f"Clear visual representing {label}",
                    ) for index, label in enumerate(configured_choices)],
                    responseMethod=response_modes,
                    teacherActionAfterSelection="Acknowledge the selection and provide the selected teacher-confirmed option.",
                ),
            )
        elif material_type == "emotion_scale":
            spec = RegulationScaleSpec(
                **common,
                artifactType="regulation_scale",
                content=RegulationScaleContent(
                    levels=[
                        RegulationScaleLevel(order=1, label="Ready", observableIndicators=["Available for the activity"], matchingSupportOption="Continue with confirmed supports"),
                        RegulationScaleLevel(order=2, label="Need support", observableIndicators=["Requests or indicates support"], matchingSupportOption="Offer a confirmed support or reduced task demand"),
                        RegulationScaleLevel(order=3, label="Need a break", observableIndicators=["Requests or indicates a break"], matchingSupportOption=lesson_spec.transition_plan.break_request or "Honor the confirmed break plan"),
                    ],
                    nonjudgmentalLanguage="All levels communicate useful information; no level is good or bad.",
                ),
            )
        elif material_type == "data_sheet":
            spec = GoalSpecificDataSheetSpec(
                **common,
                artifactType="goal_specific_data_sheet",
                content=GoalSpecificDataSheetContent(
                    operationalizedTargetBehavior=lesson_spec.goal.observable_behavior,
                    trialDefinition=lesson_spec.data_plan.trial_definition,
                    exactColumns=list(dict.fromkeys([*lesson_spec.data_plan.measures, "notes"])),
                    responseCoding=["successful", "prompted", "not observed", "break/stop honored"],
                    promptLevelDefinitions=self._prompt_level_definitions(lesson_spec),
                    independenceRule=lesson_spec.data_plan.independence_definition,
                    summaryCalculationsOrTotals=[
                        "Total opportunities",
                        "Successful opportunities",
                        "Independent successful opportunities",
                        "Successful opportunities by context and response mode",
                    ],
                ),
            )
        else:
            if not response_modes:
                return None
            spec = LessonSummarySpec(
                **common,
                artifactType="lesson_summary",
                content=LessonSummaryContent(
                    goal=lesson_spec.goal.display_text,
                    observableTarget=lesson_spec.goal.observable_behavior,
                    contextsPracticed=[item.label for item in contexts] or [
                        lesson_spec.goal.conditions or lesson_spec.goal.display_text
                    ],
                    responseModesUsed=response_modes,
                    opportunityTotal=total,
                    successfulOpportunityTotal=0,
                    independenceSummary="Record successful independent responses using the LessonSpec independence rule.",
                    # Prompt-fading decisions are teacher-facing instructions,
                    # not provenance-only metadata. Keep the exact reviewed
                    # fade rule beside the prompt sequence for rendering.
                    promptsUsed=list(
                        dict.fromkeys(
                            [
                                *prompt_sequence,
                                lesson_spec.prompting_plan.fade_rule,
                            ]
                        )
                    ),
                    reinforcementDelivered=(
                        reward
                        or lesson_spec.reinforcement_plan.specific_praise
                        or "No earned reinforcement is specified in this LessonSpec."
                    ),
                    regulationAndBreakNotes="Record break requests, whether they were honored, duration, and return support.",
                    nextStep="Compare performance with the confirmed success criterion and select the next context or support adjustment.",
                    reportingFields=[
                        "Opportunities completed",
                        "Independent requests",
                        "AAC requests",
                        "Spoken requests",
                        "Lowest prompt used",
                        "Returned after break",
                        "Context with strongest performance",
                        "Context needing more support",
                        "Suggested next generalization step",
                        "Teacher notes",
                    ],
                ),
            )

        return (
            self.validate_and_repair(
                spec,
                lesson_spec,
                repair,
                max_attempts=self.config.MAX_MATERIAL_REPAIR_ATTEMPTS,
            )
            if repair is not None
            else self.require_valid(spec, lesson_spec)
        )

    def validate(
        self,
        material_spec: MaterialSpec,
        lesson_spec: LessonSpec,
        legacy_content: dict | None = None,
    ) -> MaterialValidationResult:
        issues: list[MaterialValidationIssue] = []

        def issue(path: str, code: str, message: str, remediation: str) -> None:
            issues.append(MaterialValidationIssue(fieldPath=path, code=code, message=message, remediation=remediation))

        if not material_spec.instructional_purpose.strip():
            issue("instructionalPurpose", "missing_instructional_purpose", "Instructional purpose is required.", "State how this material supports the observable goal.")
        if not material_spec.profile_factor_ids:
            issue("profileFactorIds", "missing_profile_provenance", "Profile provenance is required.", "Attach confirmed profile factor IDs or the source profile revision.")
        if not material_spec.decision_ids:
            issue("decisionIds", "missing_decision_provenance", "Teacher-decision provenance is required.", "Attach the confirmed material decision IDs.")
        if material_spec.lesson_spec_id != lesson_spec.id or material_spec.lesson_spec_revision != lesson_spec.revision:
            issue("lessonSpecRevision", "stale_lesson_spec_revision", "Material was validated against a different LessonSpec revision.", "Regenerate or explicitly repair this material from the current LessonSpec.")

        text_values = self._text_values({
            "materialSpec": material_spec.content.model_dump(mode="json", by_alias=True),
            "legacyProjection": legacy_content or {},
        })
        blocking_assumptions = [item.text for item in lesson_spec.unresolved_assumptions if item.blocking]
        for phrase in self.placeholder_phrases:
            matched = any(
                self._norm(value) == self._norm(phrase)
                if phrase in {"specific praise", "selected reinforcer"}
                else self._norm(phrase) in self._norm(value)
                for value in text_values
            )
            if not matched:
                continue
            if phrase == "to be confirmed" and any(phrase in item.casefold() for item in blocking_assumptions):
                continue
            issue("content", "placeholder_content", f"Placeholder phrase is not review-ready: {phrase}.", "Replace it with concrete LessonSpec-supported content or record a blocking assumption.")

        validator_name = self.validator_registry.get(material_spec.artifact_type)
        if validator_name:
            getattr(self, validator_name)(material_spec, lesson_spec, issue)
        return MaterialValidationResult(status="failed" if issues else "passed", issues=issues)

    def validate_safety(
        self,
        material_spec: MaterialSpec,
        lesson_spec: LessonSpec,
        semantic: MaterialValidationResult | None = None,
        legacy_content: dict | None = None,
    ) -> MaterialSafetyValidationResult:
        semantic = semantic or self.validate(material_spec, lesson_spec, legacy_content)
        issues: list[StructuredSafetyIssue] = []
        category_by_code = {
            "prohibited_prompting": "prompting",
            "prohibited_reinforcer": "reinforcement",
            "communication_mode_mismatch": "access",
            "speech_only_requirement": "access",
            "inaccessible_motor_requirement": "access",
            "excluded_audio_feature": "access",
            "blocking_assumption": "unsupported_assumption",
        }
        for index, semantic_issue in enumerate(semantic.issues, 1):
            issues.append(StructuredSafetyIssue(
                id=f"{material_spec.id}-safety-{index}",
                scope="material",
                materialId=material_spec.id,
                category=category_by_code.get(semantic_issue.code, "semantic_inconsistency"),
                severity="blocking",
                message=semantic_issue.message,
                profileFactorIds=material_spec.profile_factor_ids,
                lessonSpecPath=self._lesson_path_for_code(semantic_issue.code),
                materialSpecPath=semantic_issue.field_path,
                suggestedCorrection=semantic_issue.remediation,
                detectedAtRevision=material_spec.revision,
            ))
        text = json.dumps({
            "content": material_spec.content.model_dump(mode="json", by_alias=True),
            "legacy": legacy_content or {},
        }, sort_keys=True, default=str).casefold()
        lexical = {
            "coercion": ("force the learner", "forced eye contact", "withhold communication", "hand over hand until"),
            "emotional_safety": ("punish", "shame", "humiliate"),
            "privacy": ("diagnosis is", "full legal name", "home address"),
        }
        for category, terms in lexical.items():
            for term in terms:
                if term in text:
                    issues.append(StructuredSafetyIssue(
                        id=f"{material_spec.id}-{category}-{len(issues) + 1}", scope="material",
                        materialId=material_spec.id, category=category, severity="blocking",
                        message=f"Material contains unsafe {category.replace('_', ' ')} content: {term}.",
                        profileFactorIds=material_spec.profile_factor_ids,
                        lessonSpecPath="safetyConstraints", materialSpecPath="content",
                        suggestedCorrection="Remove the unsafe wording and revalidate the current revision.",
                        detectedAtRevision=material_spec.revision,
                    ))
        return MaterialSafetyValidationResult(status="failed" if any(item.severity == "blocking" for item in issues) else "passed", issues=issues)

    def require_valid(self, material_spec: MaterialSpec, lesson_spec: LessonSpec) -> MaterialSpec:
        result = self.validate(material_spec, lesson_spec)
        safety = self.validate_safety(material_spec, lesson_spec, result)
        if result.status == "failed":
            raise ValidationError(
                "MaterialSpec validation failed",
                payload={"materialSpecId": material_spec.id, **result.model_dump(mode="json", by_alias=True)},
            )
        return material_spec.model_copy(update={
            "semantic_validation": result,
            "safety_validation": safety,
        })

    def validate_and_repair(
        self,
        material_spec: MaterialSpec,
        lesson_spec: LessonSpec,
        repair: Callable[[MaterialSpec, list[MaterialValidationIssue], LessonSpec], MaterialSpec],
        *,
        max_attempts: int = 2,
    ) -> MaterialSpec:
        current = material_spec
        for attempt in range(max_attempts + 1):
            semantic = self.validate(current, lesson_spec)
            safety = self.validate_safety(current, lesson_spec, semantic)
            if semantic.status == "passed" and safety.status == "passed":
                return current.model_copy(update={
                    "repair_attempts": attempt,
                    "repair_status": "repaired" if attempt else "not_needed",
                    "semantic_validation": semantic,
                    "safety_validation": safety,
                })
            if attempt == max_attempts:
                failed = current.model_copy(update={
                    "repair_attempts": attempt,
                    "repair_status": "exhausted",
                    "semantic_validation": semantic,
                    "safety_validation": safety,
                })
                raise ValidationError(
                    "MaterialSpec repair exhausted; teacher action is required",
                    payload={
                        "materialSpec": failed.model_dump(mode="json", by_alias=True),
                        "attempts": attempt,
                        "issues": semantic.model_dump(mode="json", by_alias=True)["issues"],
                    },
                )
            candidate = repair(current, semantic.issues, lesson_spec)
            if type(candidate) is not type(current):
                raise ValidationError("MaterialSpec repair cannot change artifact type")
            # IDs, lineage, design constraints, selected purpose, and approval
            # are application-owned. A repair may change only typed content.
            current = candidate.model_copy(update={
                "id": current.id,
                "schema_version": current.schema_version,
                "revision": current.revision,
                "package_id": current.package_id,
                "lesson_spec_id": current.lesson_spec_id,
                "lesson_spec_revision": current.lesson_spec_revision,
                "learner_id": current.learner_id,
                "artifact_type": current.artifact_type,
                "title": current.title,
                "instructional_purpose": current.instructional_purpose,
                "profile_factor_ids": current.profile_factor_ids,
                "decision_ids": current.decision_ids,
                "source_material_id": current.source_material_id,
                "design_constraints": current.design_constraints,
                "visual_asset_requests": current.visual_asset_requests,
                "teacher_editable_fields": current.teacher_editable_fields,
                "approval": current.approval,
            })
        raise AssertionError("bounded repair loop did not terminate")

    def _validate_personalized_activity(self, spec, lesson_spec, issue) -> None:
        content = spec.content
        if self._norm(content.instructional_objective) != self._norm(lesson_spec.goal.display_text):
            issue("content.instructionalObjective", "goal_mismatch", "Activity objective disagrees with LessonSpec.", "Use the confirmed goal verbatim.")
        action = self._norm(content.learner_action)
        inaccessible = []
        for requirement in lesson_spec.access_plan.motor_access_alternatives:
            normalized = self._norm(requirement)
            if "handwriting" in normalized and "handwrit" in action:
                inaccessible.append("handwriting")
            if "cutting" in normalized and ("cut" in action or "scissor" in action):
                inaccessible.append("cutting")
        if inaccessible:
            issue("content.learnerAction", "inaccessible_motor_requirement", f"Activity requires inaccessible motor actions: {', '.join(inaccessible)}.", "Use the confirmed motor-access alternatives.")
        if not content.completion_criterion.strip():
            issue("content.completionCriterion", "missing_completion_criterion", "Activity has no completion criterion.", "Use the LessonSpec success criterion.")

    def _validate_communication_card(self, spec, lesson_spec, issue) -> None:
        content = spec.content
        actual = {self._norm(item) for item in content.accepted_communication_modes}
        expected = {self._norm(item) for item in lesson_spec.goal.accepted_response_modes}
        if actual != expected:
            issue("content.acceptedCommunicationModes", "communication_mode_mismatch", "Communication card modes disagree with LessonSpec.", "Preserve all accepted response modes equally.")
        if "aac" in expected and actual == {"speech"}:
            issue("content.acceptedCommunicationModes", "speech_only_requirement", "Card requires speech despite an accepted AAC response.", "Accept speech and AAC equally.")
        duration = lesson_spec.transition_plan.break_duration_minutes
        response = self._norm(content.teacher_response_after_use)
        break_request = self._norm(lesson_spec.transition_plan.break_request)
        is_break_card = bool(
            break_request
            and (
                self._norm(content.exact_communication_phrase) in break_request
                or break_request in self._norm(content.exact_communication_phrase)
            )
        )
        if duration and is_break_card and (str(duration) not in response or "timer" not in response):
            issue("content.teacherResponseAfterUse", "missing_break_response", "Communication-card teacher action does not start the confirmed visual timer.", "Honor the request and begin the confirmed visual timer.")

    def _validate_first_then_board(self, spec, lesson_spec, issue) -> None:
        request = next(
            (
                item
                for item in lesson_spec.material_requests
                if item.material_type == "first_then_board"
            ),
            None,
        )
        configured_then = (
            str(
                {
                    item.key: item.value
                    for item in request.configuration
                }.get("thenOutcome")
                or ""
            ).strip()
            if request is not None
            else ""
        )
        allowed = [
            configured_then,
            lesson_spec.reinforcement_plan.earned_reward,
            lesson_spec.transition_plan.return_support,
            lesson_spec.transition_plan.break_request,
        ]
        then_value = self._norm(spec.content.then_outcome)
        if not any(value and (then_value in self._norm(value) or self._norm(value) in then_value) for value in allowed):
            issue("content.thenOutcome", "then_plan_mismatch", "THEN outcome does not match the reinforcement or transition plan.", "Use the selected reward or confirmed transition outcome verbatim.")

    def _validate_token_board(self, spec, lesson_spec, issue) -> None:
        content = spec.content
        expected = lesson_spec.reinforcement_plan.token_count
        if expected is not None and content.exact_token_count != expected:
            issue("content.exactTokenCount", "wrong_token_count", "Token count disagrees with LessonSpec.", f"Use exactly {expected} tokens.")
        if content.earned_reward != lesson_spec.reinforcement_plan.earned_reward:
            issue("content.earnedReward", "wrong_reward", "Reward disagrees with LessonSpec.", "Use the confirmed LessonSpec reward verbatim.")
        if any(self._contains_equivalent(content.earned_reward, item) for item in lesson_spec.reinforcement_plan.excluded_reinforcers):
            issue("content.earnedReward", "prohibited_reinforcer", "Token board reward is excluded by the learner profile.", "Use a confirmed, non-excluded reward.")
        if content.specific_praise != lesson_spec.reinforcement_plan.specific_praise:
            issue("content.specificPraise", "wrong_specific_praise", "Token-board praise disagrees with LessonSpec.", "Use the confirmed specific praise verbatim.")

    def _validate_visual_timer(self, spec, lesson_spec, issue) -> None:
        expected = lesson_spec.transition_plan.break_duration_minutes
        if expected is not None and spec.content.duration_minutes != expected:
            issue("content.durationMinutes", "timer_duration_mismatch", "Timer duration disagrees with the transition plan.", f"Use exactly {expected} minutes.")
        if lesson_spec.access_plan.prohibited_audio_features and spec.content.audio_allowed:
            issue("content.audioAllowed", "excluded_audio_feature", "Timer enables audio despite confirmed audio exclusions.", "Disable audio and use a visible countdown.")

    def _validate_scenario_cards(self, spec, lesson_spec, issue) -> None:
        required = lesson_spec.goal.success_criterion.required_contexts if lesson_spec.goal.success_criterion else 1
        keys = [
            (self._norm(item.context), self._norm(item.trigger_or_transition))
            for item in spec.content.scenarios
        ]
        if len(keys) != len(set(keys)):
            issue("content.scenarios", "duplicate_scenarios", "Scenario cards contain duplicated contexts and transitions.", "Provide distinct teacher-selected practice contexts.")
        if lesson_spec.generalization_plan.required and len(spec.content.scenarios) < required:
            issue("content.scenarios", "insufficient_scenarios", f"LessonSpec requires {required} distinct contexts.", f"Provide at least {required} scenario cards.")
        if any(not item.expected_response.strip() for item in spec.content.scenarios):
            issue("content.scenarios", "missing_expected_response", "One or more scenarios lack the expected learner response.", "Use the observable LessonSpec response on every card.")
        expected_modes = {self._norm(item) for item in lesson_spec.goal.accepted_response_modes}
        for index, scenario in enumerate(spec.content.scenarios):
            if {self._norm(item) for item in scenario.accepted_modalities} != expected_modes:
                issue(f"content.scenarios.{index}.acceptedModalities", "communication_mode_mismatch", "Scenario response modes disagree with LessonSpec.", "Preserve all accepted response modes.")
            for prompt in scenario.prompt_sequence:
                if any(self._contains_equivalent(prompt, prohibited) for prohibited in lesson_spec.prompting_plan.prohibited_prompts):
                    issue(f"content.scenarios.{index}.promptSequence", "prohibited_prompting", "Scenario includes prohibited prompting.", "Use only the confirmed prompting sequence.")
            if lesson_spec.prompting_plan.wait_time_seconds and scenario.wait_time_seconds != lesson_spec.prompting_plan.wait_time_seconds:
                issue(f"content.scenarios.{index}.waitTimeSeconds", "wait_time_mismatch", "Scenario wait time disagrees with LessonSpec.", "Use the confirmed processing interval.")
            if not all((scenario.visual_cue, scenario.teacher_wording, scenario.break_outcome, scenario.return_support, scenario.generalization_label)):
                issue(f"content.scenarios.{index}", "incomplete_scenario_card", "Scenario card is not independently executable.", "Include cue, teacher wording, outcome, return support, and generalization label.")

    def _validate_choice_board(self, spec, lesson_spec, issue) -> None:
        labels = [self._norm(item.label) for item in spec.content.choices]
        if len(labels) < 2 or len(labels) != len(set(labels)):
            issue("content.choices", "invalid_choices", "Choice board needs at least two distinct actual choices.", "Provide two or more distinct teacher-selected options.")
        maximum = lesson_spec.access_plan.maximum_primary_visual_choices
        if maximum is not None and len(labels) > maximum:
            issue("content.choices", "choice_limit_exceeded", "Choice board exceeds the confirmed visual-choice limit.", f"Use no more than {maximum} choices.")

    def _validate_regulation_scale(self, spec, lesson_spec, issue) -> None:
        levels = spec.content.levels
        orders = [item.order for item in levels]
        if len(levels) < 3 or orders != sorted(orders):
            issue("content.levels", "invalid_regulation_levels", "Regulation scale requires at least three ordered levels.", "Provide three or more ordered, nonjudgmental levels.")

    def _validate_data_sheet(self, spec, lesson_spec, issue) -> None:
        content = spec.content
        if self._norm(content.operationalized_target_behavior) != self._norm(lesson_spec.goal.observable_behavior):
            issue("content.operationalizedTargetBehavior", "data_sheet_goal_mismatch", "Data sheet target is unrelated to the LessonSpec goal.", "Use the observable LessonSpec target verbatim.")
        missing = [item for item in lesson_spec.data_plan.measures if item not in content.exact_columns]
        if missing:
            issue("content.exactColumns", "missing_goal_measure", f"Missing required goal measures: {', '.join(missing)}.", "Include every LessonSpec data measure.")
        if not content.independence_rule.strip():
            issue("content.independenceRule", "missing_independence_rule", "Data sheet lacks an independence rule.", "Use the LessonSpec independence definition.")
        if not content.prompt_level_definitions:
            issue("content.promptLevelDefinitions", "missing_prompt_coding", "Data sheet lacks prompt coding.", "Include the LessonSpec prompt levels.")

    def _validate_lesson_summary(self, spec, lesson_spec, issue) -> None:
        if self._norm(spec.content.goal) != self._norm(lesson_spec.goal.display_text):
            issue("content.goal", "goal_mismatch", "Summary goal disagrees with LessonSpec.", "Use the current confirmed goal.")
        expected = {
            "opportunities completed", "independent requests", "aac requests",
            "spoken requests", "lowest prompt used", "returned after break",
            "context with strongest performance", "context needing more support",
            "suggested next generalization step", "teacher notes",
        }
        actual = {self._norm(item) for item in spec.content.reporting_fields}
        missing = sorted(expected - actual)
        if missing:
            issue("content.reportingFields", "incomplete_goal_summary", f"Lesson summary is missing: {', '.join(missing)}.", "Include every goal-specific outcome and next-step field.")

    @staticmethod
    def _lesson_path_for_code(code: str) -> str:
        return {
            "wrong_token_count": "reinforcementPlan.tokenCount",
            "wrong_reward": "reinforcementPlan.earnedReward",
            "prohibited_reinforcer": "reinforcementPlan.excludedReinforcers",
            "prohibited_prompting": "promptingPlan.prohibitedPrompts",
            "communication_mode_mismatch": "goal.acceptedResponseModes",
            "speech_only_requirement": "goal.acceptedResponseModes",
            "inaccessible_motor_requirement": "accessPlan.motorAccessAlternatives",
            "excluded_audio_feature": "accessPlan.prohibitedAudioFeatures",
            "stale_lesson_spec_revision": "revision",
        }.get(code, "goal")

    def _common(
        self,
        material_id: str,
        package_id: str,
        title: str,
        request: LessonSpecMaterialRequest,
        lesson_spec: LessonSpec,
        material_type: str,
        visual_asset_requests: list[MaterialVisualAssetRequest],
    ) -> dict:
        return {
            "id": material_id,
            "packageId": package_id,
            "lessonSpecId": lesson_spec.id,
            "lessonSpecRevision": lesson_spec.revision,
            "learnerId": lesson_spec.learner_id,
            "title": title,
            "instructionalPurpose": request.instructional_purpose,
            "profileFactorIds": request.profile_factor_ids or lesson_spec.profile_factor_ids or [f"profile-revision:{lesson_spec.profile_revision}"],
            "decisionIds": lesson_spec.decision_ids,
            "sourceMaterialId": request.library_material_id,
            "designConstraints": MaterialDesignConstraints(
                orientation="landscape" if material_type in {
                    "token_board", "first_then_board", "data_sheet",
                    "blue_line_activity", "scenario_cards",
                } else "portrait",
                maximumPrimaryChoices=lesson_spec.access_plan.maximum_primary_visual_choices,
                layoutRequirements=lesson_spec.access_plan.layout_requirements,
                prohibitedVisualFeatures=lesson_spec.access_plan.prohibited_visual_features,
                prohibitedAudioFeatures=lesson_spec.access_plan.prohibited_audio_features,
                motorAccessRequirements=lesson_spec.access_plan.motor_access_alternatives,
                minimumTouchTarget="Teacher-confirmed accessible touch target" if material_type in {"visual_card", "help_card", "break_card", "choice_board"} else None,
            ),
            "visualAssetRequests": visual_asset_requests,
            "teacherEditableFields": ["title", "content", "designConstraints"],
            "approval": MaterialApproval(),
        }

    @staticmethod
    def _communication_phrase(lesson_spec: LessonSpec, material_type: str) -> str:
        for value in (lesson_spec.goal.observable_behavior, lesson_spec.goal.display_text):
            quoted = re.search(r"[“\"]([^”\"]+)[”\"]", value)
            if quoted:
                return quoted.group(1).strip()
        if material_type == "break_card" and "break" in lesson_spec.goal.observable_behavior.casefold():
            return "Break, please"
        if material_type == "help_card" and "help" in lesson_spec.goal.observable_behavior.casefold():
            return "Help, please"
        if material_type == "help_card":
            return "Help, please."
        if material_type == "break_card":
            return "Break, please."
        return lesson_spec.goal.observable_behavior.strip()

    @staticmethod
    def _configured_choices(request: LessonSpecMaterialRequest) -> list[str]:
        choices: list[str] = []
        for item in request.configuration:
            if not item.key.casefold().startswith("choice") or item.value in (None, ""):
                continue
            if isinstance(item.value, str) and "," in item.value:
                choices.extend(value.strip() for value in item.value.split(",") if value.strip())
            else:
                choices.append(str(item.value).strip())
        return list(dict.fromkeys(choices))

    @staticmethod
    def _prompt_level_definitions(lesson_spec: LessonSpec) -> list[str]:
        definitions = [
            f"Independent: {lesson_spec.data_plan.independence_definition}"
        ]
        source = " ".join([
            *lesson_spec.data_plan.prompt_levels,
            *lesson_spec.prompting_plan.sequence,
        ]).casefold()
        candidates = (
            ("Visual or gestural cue", "Show or point to the existing visual cue without modeling the response."),
            ("Model", "Demonstrate the communication response once, then provide another opportunity."),
            ("Brief verbal prompt", "Use the shortest confirmed verbal cue, then wait again."),
        )
        for name, definition in candidates:
            if any(term in source for term in name.casefold().split(" or ")):
                definitions.append(f"{name}: {definition}")
        return definitions

    @staticmethod
    def _prompt_sequence_steps(values: list[str]) -> list[str]:
        steps: list[str] = []
        for value in values:
            steps.extend(
                item.strip().rstrip(".")
                for item in re.split(r",|\bthen\b", value, flags=re.I)
                if item.strip()
            )
        return list(dict.fromkeys(steps))

    @staticmethod
    def _norm(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())

    @classmethod
    def _text_values(cls, value) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [text for item in value.values() for text in cls._text_values(item)]
        if isinstance(value, (list, tuple)):
            return [text for item in value for text in cls._text_values(item)]
        return []

    @classmethod
    def _contains_equivalent(cls, value: str, prohibited: str) -> bool:
        left, right = cls._norm(value), cls._norm(prohibited)
        return bool(left and right and (left in right or right in left))
