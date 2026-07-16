from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from app.core.config import Settings, settings
from app.integrations.ai_provider import V2AIProvider
from app.schemas.v2_dto import (
    AIQuestion,
    AIQuestionOption,
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraft,
    LessonDesignDraftDto,
    ProfileExtractionResult,
    ProfileSignal,
)
from app.skills.registry import SkillRegistry, get_skill_registry
from app.services.v2_ai_context_service import build_ai_safe_profile


def _option(
    option_id: str,
    label: str,
    icon: str,
    recommended: bool = False,
    description: str = "",
) -> AIQuestionOption:
    return AIQuestionOption(
        id=option_id,
        label=label,
        value=label,
        icon=icon,
        recommended=recommended,
        description=(
            description
            or (
                "Suggested from the teacher-confirmed profile and current request."
                if recommended
                else "Teacher-selectable option."
            )
        ),
        source="ai_generated",
    )


class MockV2AIProvider(V2AIProvider):
    """Deterministic provider used until a real safeguarded provider is configured."""

    provider_name = "mock"

    def __init__(
        self,
        config: Settings = settings,
        registry: SkillRegistry | None = None,
    ) -> None:
        self._settings = config
        self._registry = registry or get_skill_registry(config)
        self.last_generation_metadata = None
        self.generation_metadata_by_skill = {}

    def _mark_local_mock(self, skill_id: str) -> None:
        self._record_generation(
            self._registry,
            skill_id,
            status="local_mock",
            model="deterministic-local-mock",
            output_source="local_mock",
        )

    def extract_profile(
        self, learner: LearnerProfile, records: list[LearnerRecord]
    ) -> ProfileExtractionResult:
        self._mark_local_mock("learner_profile")
        extracted = learner.model_copy(deep=True)
        signals: list[ProfileSignal] = []
        record_fingerprints: dict[str, str] = {}

        def add_signal(
            category: str,
            label: str,
            confidence: float,
            evidence: str,
            record_id: str,
            evidence_type: str = "documented_fact",
            contradiction_state: str = "none",
        ) -> None:
            key = (category, label.casefold(), record_id)
            if any(
                (item.category, item.label.casefold(), item.source_record_id) == key
                for item in signals
            ):
                return
            signals.append(
                ProfileSignal(
                    id=(
                        f"signal-{record_id}-{category}-"
                        f"{record_fingerprints.get(record_id, 'unknown')[:10]}-"
                        f"{len(signals) + 1}"
                    ),
                    category=category,
                    label=label,
                    confidence=confidence,
                    status="suggested",
                    evidence=evidence,
                    source_record_id=record_id,
                    summary=label,
                    evidence_type=evidence_type,
                    source_location="record text",
                    contradiction_state=contradiction_state,
                    suggested_profile_value=label,
                    teacher_review_state="pending",
                    evidence_fingerprint=(
                        f"{record_id}:{category}:{label.casefold()}:"
                        f"{record_fingerprints.get(record_id, 'unknown')}"
                    ),
                )
            )

        interest_terms = {
            "vehicle": "Vehicles",
            "car": "Cars",
            "puzzle": "Puzzles",
            "bubble": "Bubbles",
            "music": "Music",
            "animal": "Animals",
            "building block": "Building blocks",
        }
        for record in records:
            text = record.extracted_text.casefold()
            record_fingerprints[record.id] = sha256(
                record.extracted_text.encode("utf-8")
            ).hexdigest()[:16]
            evidence_type = (
                "outdated_evidence"
                if any(
                    token in text
                    for token in ("outdated", "no longer current", "historical record")
                )
                else (
                    "contradiction"
                    if any(
                        token in text
                        for token in (
                            "conflicting information",
                            "contradicts",
                            "however, a newer",
                        )
                    )
                    else (
                        "caregiver_report"
                        if "caregiver report" in text or "parent report" in text
                        else (
                            "teacher_report"
                            if "teacher report" in text
                            else (
                                "observation"
                                if "observed" in text or "session note" in text
                                else "documented_fact"
                            )
                        )
                    )
                )
            )
            contradiction_state = (
                "outdated"
                if evidence_type == "outdated_evidence"
                else "conflicting" if evidence_type == "contradiction" else "none"
            )
            for term, label in interest_terms.items():
                if term in text:
                    add_signal(
                        "interest",
                        label,
                        0.82 if "interest" in text or "preferred" in text else 0.68,
                        f"The record links engagement or preference with {label.lower()} activities.",
                        record.id,
                        evidence_type,
                        contradiction_state,
                    )
            if "visual" in text:
                add_signal(
                    "support_need",
                    "Visual supports",
                    0.9,
                    "The record directly describes benefit from visual support.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
                add_signal(
                    "receptive_support",
                    "Visual information",
                    0.86,
                    "The record describes visual information as a receptive support.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
                add_signal(
                    "effective_support",
                    "Visual support",
                    0.84,
                    "The record reports visual support as helpful for participation.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
            if "short phrase" in text:
                add_signal(
                    "communication",
                    "Short phrases",
                    0.9,
                    "The record directly describes communication using short phrases.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
                add_signal(
                    "expressive_support",
                    "Short phrase response",
                    0.86,
                    "The record describes short phrases as an available expressive response.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
            if "wait time" in text:
                add_signal(
                    "prompting",
                    "Wait before prompting",
                    0.86,
                    "The record recommends wait time before adding support.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
            if "goal" in text and "request" in text:
                add_signal(
                    "goal",
                    "Requesting help",
                    0.86,
                    "The record identifies requesting help as a current instructional goal.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
            if "aac" in text or "device" in text:
                add_signal(
                    "response_option",
                    "AAC response available",
                    0.86,
                    "The record describes AAC or device access for responding.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
            if "break" in text:
                add_signal(
                    "break_preference",
                    "Brief break option",
                    0.76,
                    "The record describes a break as an instructional support.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
            if "independent" in text:
                add_signal(
                    "independence",
                    "Independent responses observed",
                    0.72,
                    "The record describes at least one independent response.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )
            if any(
                term in text
                for term in ("short activity", "brief activity", "short structured")
            ):
                add_signal(
                    "attention_engagement",
                    "Brief structured activities",
                    0.8,
                    "The record links engagement with brief structured activities.",
                    record.id,
                    evidence_type,
                    contradiction_state,
                )

        high_confidence_interests = [
            item.label
            for item in signals
            if item.category == "interest" and item.confidence >= 0.75
        ]
        support_signals = [
            item.label
            for item in signals
            if item.category == "support_need" and item.confidence >= 0.75
        ]
        communication_signals = [
            item.label
            for item in signals
            if item.category == "communication" and item.confidence >= 0.75
        ]
        prompting_signals = [
            item.label
            for item in signals
            if item.category == "prompting" and item.confidence >= 0.75
        ]
        goal_signals = [
            item.label
            for item in signals
            if item.category == "goal" and item.confidence >= 0.75
        ]
        if not extracted.interests and high_confidence_interests:
            extracted.interests = list(dict.fromkeys(high_confidence_interests))
        if not extracted.support_needs and support_signals:
            extracted.support_needs = list(dict.fromkeys(support_signals))
        if not extracted.communication_mode and communication_signals:
            extracted.communication_mode = communication_signals[0]
        if not extracted.prompting_preferences and prompting_signals:
            extracted.prompting_preferences = prompting_signals
        if not extracted.current_goals and goal_signals:
            extracted.current_goals = goal_signals
        response_signals = [
            item.label
            for item in signals
            if item.category == "response_option" and item.confidence >= 0.75
        ]
        break_signals = [
            item.label
            for item in signals
            if item.category == "break_preference" and item.confidence >= 0.75
        ]
        if not extracted.response_options and response_signals:
            extracted.response_options = response_signals
        if not extracted.break_preferences and break_signals:
            extracted.break_preferences = break_signals
        for field_name, category in (
            ("receptive_supports", "receptive_support"),
            ("expressive_supports", "expressive_support"),
            ("effective_supports", "effective_support"),
        ):
            values = [
                item.label
                for item in signals
                if item.category == category and item.confidence >= 0.75
            ]
            if not getattr(extracted, field_name) and values:
                setattr(extracted, field_name, list(dict.fromkeys(values)))
        independence_signals = [
            item.label
            for item in signals
            if item.category == "independence" and item.confidence >= 0.75
        ]
        if not extracted.independence_profile and independence_signals:
            extracted.independence_profile = independence_signals[0]
        domain_values = {
            "strengths": extracted.strengths,
            "interests": extracted.interests or high_confidence_interests,
            "communicationModalities": extracted.communication_mode,
            "responseOptions": extracted.response_options,
            "receptiveSupports": extracted.receptive_supports,
            "expressiveSupports": extracted.expressive_supports,
            "attentionAndEngagement": extracted.attention_profile,
            "sensoryAndEnvironment": [
                *extracted.sensory_preferences,
                *extracted.environmental_considerations,
            ],
            "confirmedMotivators": extracted.reinforcement_preferences,
            "promptingHistory": extracted.prompting_preferences,
            "effectiveSupports": extracted.effective_supports,
            "ineffectiveSupports": extracted.ineffective_supports,
            "independence": extracted.independence_profile,
            "masteredSkills": extracted.mastered_skills,
            "emergingSkills": extracted.emerging_skills,
            "activeInstructionalGoals": extracted.current_goals,
            "generalization": extracted.generalization_profile,
            "breakPreferences": extracted.break_preferences,
            "classroomBarriers": extracted.classroom_barriers,
        }
        unknown_fields = [field for field, value in domain_values.items() if not value]
        extracted.profile_signals = signals
        extracted.unknown_fields = unknown_fields
        insights = [
            "Use visual supports",
            "Keep activities short",
            "Add multiple examples",
        ]
        return ProfileExtractionResult(
            learner=extracted,
            profileSignals=signals,
            unknownFields=unknown_fields,
            insights=insights,
        )

    def generate_lesson_questions(
        self, learner: LearnerProfile, teacher_request: str
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        self._mark_local_mock("lesson_planning")
        safe_profile = build_ai_safe_profile(learner)
        safe_interests = safe_profile["interests"]
        theme = safe_interests[0] if safe_interests else "Classroom"
        theme_lower = theme.casefold()
        if any(term in theme_lower for term in ("vehicle", "car")):
            scenario_labels = ["Toy car stuck", "Closed box", "Backpack zipper"]
        elif "emotion" in theme_lower:
            scenario_labels = [
                "Emotion card choice",
                "Classroom check-in",
                "Story picture",
            ]
        else:
            scenario_labels = ["Blocks need help", "Closed box", "Backpack zipper"]
        scenario_ids = {
            "Toy car stuck": "toy-car",
            "Closed box": "closed-box",
            "Backpack zipper": "backpack",
        }
        reinforcers = safe_profile["reinforcementPreferences"] or [
            "Teacher praise",
            "Choice time",
        ]
        questions = [
            AIQuestion(
                id="target-response",
                prompt="Does this observable target match what you want to teach?",
                helper_text="AI suggested wording from your request; confirm or edit it before generation.",
                field="goalText",
                input_type="hybrid",
                options=[
                    _option(
                        "confirm-target",
                        (
                            "Learner will ask for help using a short phrase."
                            if "help" in teacher_request.casefold()
                            else "Learner will demonstrate the requested skill in an observable opportunity."
                        ),
                        "✓",
                        True,
                    )
                ],
                selected_option_ids=[],
                allow_custom_answer=True,
                max_selections=1,
            ),
            AIQuestion(
                id="baseline",
                prompt="What is the learner doing now?",
                helper_text="Baseline is required to choose an achievable level; leave it unknown if it has not been observed.",
                field="baseline",
                input_type="single_select",
                options=[
                    _option(
                        "baseline-unknown", "Unknown — collect baseline first", "?"
                    ),
                    _option("baseline-prompted", "Responds with prompting", "↗", True),
                    _option(
                        "baseline-emerging", "Sometimes responds independently", "◔"
                    ),
                ],
                selected_option_ids=[],
                allow_custom_answer=True,
                max_selections=1,
            ),
            AIQuestion(
                id="response-level",
                prompt="What response level feels achievable for this lesson?",
                helper_text="Choose the level you want to model and reinforce today.",
                field="responseLevel",
                input_type="single_select",
                options=[
                    _option("single-word", "Single word", "①"),
                    _option("short-phrase", "Short phrase", "💬", True),
                    _option("full-sentence", "Full sentence", "▤"),
                ],
                selected_option_ids=["short-phrase"],
                allow_custom_answer=True,
                max_selections=1,
            ),
            AIQuestion(
                id="scenarios",
                prompt="Where should the learner practice asking for help?",
                helper_text="Choose familiar situations, then add your own if needed.",
                field="scenarios",
                input_type="multi_select",
                options=[
                    _option(
                        scenario_ids.get(label, f"scenario-{index}"),
                        label,
                        "▣",
                        index < 2,
                    )
                    for index, label in enumerate(scenario_labels)
                ],
                selected_option_ids=[
                    scenario_ids.get(label, f"scenario-{index}")
                    for index, label in enumerate(scenario_labels)
                ],
                allow_custom_answer=True,
                max_selections=5,
            ),
            AIQuestion(
                id="materials",
                prompt="Which materials should be included in the lesson kit?",
                helper_text="Select the printable supports you want to review and edit.",
                field="selectedMaterials",
                input_type="hybrid",
                options=[
                    _option("visual-cards", "Visual Cards", "▧", True),
                    _option("help-card", "Help Card", "💬", True),
                    _option("token-board", "Token Board", "☆", True),
                    _option("data-sheet", "Data Sheet", "▦", True),
                    _option("summary", "Summary Template", "▤", True),
                ],
                selected_option_ids=[
                    "visual-cards",
                    "help-card",
                    "token-board",
                    "data-sheet",
                    "summary",
                ],
                allow_custom_answer=True,
                max_selections=5,
            ),
            AIQuestion(
                id="reinforcer",
                prompt="What is most likely to motivate participation today?",
                helper_text="Choose one or two preferences. You remain in control of reinforcement.",
                field="reinforcementPlan",
                input_type="hybrid",
                options=[
                    _option(f"reinforcer-{index}", label, "☆", index < 2)
                    for index, label in enumerate(reinforcers[:5])
                ],
                selected_option_ids=[
                    f"reinforcer-{index}" for index in range(min(2, len(reinforcers)))
                ],
                allow_custom_answer=True,
                max_selections=2,
            ),
            AIQuestion(
                id="prompting-strategy",
                prompt="How should prompting be introduced and faded?",
                helper_text="Select strategies that preserve wait time and support independence.",
                field="promptingStart",
                input_type="hybrid",
                options=[
                    _option("least-to-most", "Least-to-most prompting", "↗", True),
                    _option("visual-first", "Visual prompt first", "▧", True),
                    _option("model-prompt", "Model prompt", "◉"),
                    _option("wait-time", "Wait time before prompt", "◷"),
                    _option("fade-verbal", "Fade verbal prompts", "↘"),
                ],
                selected_option_ids=["least-to-most", "visual-first"],
                allow_custom_answer=True,
                max_selections=3,
            ),
            AIQuestion(
                id="opportunities-duration",
                prompt="How many practice opportunities fit this session?",
                helper_text="A short set is suggested from the learner's attention profile; adjust for today.",
                field="opportunities",
                input_type="single_select",
                options=[
                    _option("opportunities-3", "3 opportunities", "③"),
                    _option("opportunities-5", "5 opportunities", "⑤", True),
                    _option("opportunities-8", "8 opportunities", "⑧"),
                ],
                selected_option_ids=["opportunities-5"],
                allow_custom_answer=True,
                max_selections=1,
            ),
            AIQuestion(
                id="duration",
                prompt="How long should the complete lesson be today?",
                helper_text="A brief duration is suggested from the reviewed attention profile; the teacher can adjust it.",
                field="duration",
                input_type="single_select",
                options=[
                    _option("duration-5", "5 min", "◷"),
                    _option("duration-10", "10–12 min", "◷", True),
                    _option("duration-15", "15 min", "◷"),
                ],
                selected_option_ids=["duration-10"],
                allow_custom_answer=True,
                max_selections=1,
            ),
            AIQuestion(
                id="prompting-limits",
                prompt="When should prompting pause or change?",
                helper_text="Confirm limits that preserve teacher judgment, communication access, and learner regulation.",
                field="promptingLimits",
                input_type="multi_select",
                options=[
                    _option("limit-distress", "Pause for signs of distress", "Ⅱ", True),
                    _option(
                        "limit-errors",
                        "Reduce difficulty after repeated errors",
                        "↘",
                        True,
                    ),
                    _option(
                        "limit-override",
                        "Teacher may override the hierarchy",
                        "✓",
                        True,
                    ),
                ],
                selected_option_ids=[
                    "limit-distress",
                    "limit-errors",
                    "limit-override",
                ],
                allow_custom_answer=True,
                max_selections=3,
            ),
            AIQuestion(
                id="error-correction",
                prompt="How should an error or no response be handled?",
                helper_text="Neutral feedback and another supported opportunity protect dignity.",
                field="errorCorrection",
                input_type="single_select",
                options=[
                    _option(
                        "neutral-retry",
                        "Neutral feedback, model, then retry",
                        "↻",
                        True,
                    ),
                    _option("pause-adjust", "Pause and reduce task difficulty", "Ⅱ"),
                ],
                selected_option_ids=["neutral-retry"],
                allow_custom_answer=True,
                max_selections=1,
            ),
            AIQuestion(
                id="data-collection",
                prompt="What should be recorded for each opportunity?",
                helper_text="Track independence and prompting, not correctness alone.",
                field="dataCollection",
                input_type="multi_select",
                options=[
                    _option("data-outcome", "Response outcome", "▦", True),
                    _option("data-prompt", "Prompt level", "↘", True),
                    _option("data-latency", "Response latency", "◷"),
                    _option(
                        "data-regulation", "Participation or regulation note", "♡", True
                    ),
                ],
                selected_option_ids=["data-outcome", "data-prompt", "data-regulation"],
                allow_custom_answer=True,
                max_selections=4,
            ),
            AIQuestion(
                id="generalization",
                prompt="Where should the skill be practiced after initial success?",
                helper_text="Use small variations across people, examples, and settings.",
                field="generalizationPlan",
                input_type="multi_select",
                options=[
                    _option("generalize-example", "Different example", "▣", True),
                    _option("generalize-person", "Different familiar adult", "♙"),
                    _option("generalize-setting", "Different familiar setting", "⌂"),
                ],
                selected_option_ids=["generalize-example"],
                allow_custom_answer=True,
                max_selections=3,
            ),
            AIQuestion(
                id="teacher-constraints",
                prompt="Any constraints for today?",
                helper_text="Optional: available time, unavailable materials, team guidance, or signs to pause.",
                field="teacherConstraints",
                input_type="free_text",
                options=[],
                selected_option_ids=[],
                allow_custom_answer=True,
                required=False,
            ),
        ]
        asks_for_help = (
            "ask for help" in teacher_request.lower()
            or "asking for help" in teacher_request.lower()
        )
        draft = LessonDesignDraft(
            id=f"draft-{learner.id}",
            learner_id=learner.id,
            goal_text=(
                "Learner will ask for help using a short phrase."
                if asks_for_help
                else "Learner will practice the requested skill with teacher support."
            ),
            response_level="Short phrase",
            scenarios=scenario_labels,
            selected_materials=[
                "Visual Cards",
                "Help Card",
                "Token Board",
                "Data Sheet",
                "Summary Template",
            ],
            theme=theme,
            duration="10–12 min",
            custom_notes=(
                f"Reinforcers: {', '.join(reinforcers[:2])}. Prompting: Visual prompt first, Least-to-most prompting."
                if asks_for_help
                else f"Teacher request: {teacher_request} Reinforcers: {', '.join(reinforcers[:2])}. Prompting: Visual prompt first, Least-to-most prompting."
            ),
            baseline="Unknown — teacher confirmation needed",
            observable_response=(
                "Requests help using a short phrase"
                if asks_for_help
                else "Performs the teacher-confirmed observable response"
            ),
            opportunities=5,
            prompting_start="Wait 5 seconds, then use visual least-to-most prompting",
            prompting_limits="Pause if distress or repeated errors occur; teacher may override",
            reinforcement_plan=f"Offer {reinforcers[0]} after the target response and preserve learner choice",
            error_correction="Neutral feedback, model the response, then provide another opportunity",
            data_collection="Record outcome, independence, prompt level, participation, and notes",
            generalization_plan="Vary examples first, then familiar people and settings",
        )
        return deepcopy(questions), draft

    def polish_lesson_brief(self, draft: LessonDesignDraft) -> str:
        self._mark_local_mock("lesson_generation")
        return "Practice the target skill across short, familiar situations with teacher-confirmed supports."

    def generate_lesson_package(
        self,
        draft: LessonDesignDraftDto,
        learner_context: dict | None = None,
    ) -> dict:
        """Deterministic fake content behind the same boundary a real model will use."""
        self._mark_local_mock("lesson_generation")
        self._record_generation(
            self._registry,
            "material_generation",
            status="local_mock",
            model="deterministic-local-mock",
            output_source="local_mock",
            set_last=False,
        )
        context = learner_context or {}
        interests = context.get("interests") or []
        support_needs = context.get("supportNeeds") or []
        communication_mode = context.get("communicationMode") or draft.responseLevel
        reinforcers = context.get("reinforcementPreferences") or ["specific praise"]
        prompting = context.get("promptingPreferences") or ["least-to-most prompting"]
        theme = draft.theme.strip() or (
            interests[0] if interests else "neutral classroom"
        )
        scenario = (
            draft.scenarios[0] if draft.scenarios else "a familiar classroom activity"
        )
        phrase = draft.responseLevel or communication_mode or "the target response"
        support_copy = ", ".join(support_needs[:2]) or "clear teacher modeling"
        selected = list(dict.fromkeys(draft.selectedMaterials))
        material_types = {
            "visual cards": "visual_card",
            "visual card": "visual_card",
            "help card": "help_card",
            "token board": "token_board",
            "data sheet": "data_sheet",
            "summary template": "summary_template",
        }
        material_titles = {
            "visual_card": "Visual Card",
            "help_card": "Help Card",
            "token_board": "Token Board",
            "data_sheet": "Data Sheet",
            "summary_template": "Summary Template",
        }
        materials = []
        for selected_name in selected:
            material_type = material_types.get(selected_name.casefold())
            if not material_type:
                continue
            if material_type == "visual_card":
                content = {
                    "phrase": phrase,
                    "instruction": f"Use during {scenario.lower()} and pause before prompting.",
                    "example": draft.goalText,
                    "teacherNote": f"Support with {support_copy}.",
                }
                image_concept = (
                    f"{draft.goalText.rstrip('.')} during {scenario.lower()}"
                )
            elif material_type == "help_card":
                content = {
                    "phrase": phrase,
                    "instruction": "Model the response, offer wait time, then fade support.",
                    "example": f"Practice during {scenario.lower()}.",
                    "teacherNote": f"Use {prompting[0]}.",
                }
                image_concept = f"requesting support during {scenario.lower()}"
            elif material_type == "token_board":
                content = {
                    "instruction": "Earn 3 tokens, then access the selected reinforcer.",
                    "reward": reinforcers[0],
                    "artwork": f"Friendly {'vehicle' if 'vehicle' in theme.casefold() else theme.lower()} artwork",
                    "tokens": 3,
                    "teacherNote": (
                        "Praise effort and reinforce each appropriate request."
                        if "ask for help" in draft.goalText.casefold()
                        else "Reinforce participation and appropriate attempts, not perfection."
                    ),
                }
                image_concept = (
                    f"simple token board with {reinforcers[0].lower()} reward"
                )
            elif material_type == "data_sheet":
                content = {
                    "columns": [
                        "Scenario",
                        "Response",
                        "Prompt level",
                        "Participation",
                        "Notes",
                    ],
                    "progressSignals": [
                        "Independence",
                        "Prompt fading",
                        "Engagement",
                        "Generalization",
                    ],
                }
                image_concept = ""
            else:
                content = {
                    "prompts": [
                        "What worked?",
                        "What small win occurred?",
                        "What support is next?",
                    ],
                    "teacherNote": "Progress may be slow or uneven; record participation and independence.",
                }
                image_concept = ""
            material = {
                "type": material_type,
                "title": material_titles[material_type],
                "content": content,
            }
            if image_concept:
                material.update(
                    {
                        "imageConcept": image_concept,
                        "imagePrompt": f"A low-clutter classroom illustration of {image_concept}. Theme: {theme}.",
                        "imageAltText": f"Classroom illustration of {image_concept}.",
                    }
                )
            materials.append(material)
        return {
            "lessonBrief": (
                f"Teach the confirmed goal across short, familiar {theme.lower()} practice "
                f"situations. Use {support_copy}, {prompting[0]}, and {reinforcers[0]}; "
                "record independence, prompt level, engagement, and regulation."
            ),
            "summaryTemplate": (
                "Record what worked, what support was needed, the learner’s smallest win, "
                "and the next step for independence, prompt fading, participation, or generalization."
            ),
            "teachingFlow": [
                {
                    "id": "warm-up",
                    "title": "Warm-up and motivation",
                    "description": f"Preview the goal using {theme.lower()} or neutral classroom materials.",
                    "duration": "2 min",
                    "teacherAction": "Show the selected support and state the goal briefly.",
                    "learnerAction": "Engages with the material in an accessible way.",
                },
                {
                    "id": "model",
                    "title": "Model asking for help",
                    "description": f"Model the target during {scenario.lower()}.",
                    "duration": "2 min",
                    "teacherAction": f"Model {phrase.lower()} and provide wait time.",
                    "learnerAction": "Observes, points, approximates, or uses the target response.",
                },
                {
                    "id": "practice",
                    "title": "Guided practice with prompts",
                    "description": "Practice across teacher-selected scenarios.",
                    "duration": "4 min",
                    "teacherAction": f"Use {prompting[0]} and fade support when possible.",
                    "learnerAction": "Practices with the confirmed response level.",
                },
                {
                    "id": "independent",
                    "title": "Independent opportunity",
                    "description": "Pause before offering support.",
                    "duration": "2 min",
                    "teacherAction": "Create one familiar opportunity and wait.",
                    "learnerAction": "Attempts the response independently or with lighter support.",
                },
                {
                    "id": "reinforce",
                    "title": "Reinforcement and data note",
                    "description": "Recognize small wins and capture multidimensional progress.",
                    "duration": "2 min",
                    "teacherAction": f"Offer {reinforcers[0]} and record prompt level and participation.",
                    "learnerAction": "Receives reinforcement and transitions with support.",
                },
            ],
            "materials": materials,
        }

    def generate_material_image(
        self,
        learner: LearnerProfile,
        material_type: str,
        prompt: str,
        style: str | None = None,
        size: str | None = None,
    ) -> dict:
        self._mark_local_mock("image_generation")
        prompt_used = prompt.strip()
        if style and style.strip():
            prompt_used = f"{prompt_used} Style: {style.strip()}."
        return {
            "imageId": f"mock-image-{learner.id}-{material_type}",
            "status": "mock",
            "imageUrl": None,
            "imageBase64": None,
            "promptUsed": prompt_used,
            "fallbackUsed": False,
        }
