from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.schemas.v2_dto import LessonDesignDraftDto


@dataclass(frozen=True)
class MaterialBlueprint:
    """Professional intent and minimum construction rules for one material type."""

    material_type: str
    display_name: str
    instructional_purpose: str
    required_content: tuple[str, ...]
    professional_rules: tuple[str, ...]
    teacher_directions: tuple[str, ...]


class V2MaterialBlueprintService:
    """Goal-to-kit resolver and extensible catalog of printable supports.

    A lesson kit is selected by instructional function. Artwork personalizes the
    kit, but it does not define the kit or replace exact, programmatic content.
    """

    CORE_BUNDLES: dict[str, tuple[str, ...]] = {
        "counting": (
            "quantity_cards",
            "number_cards",
            "matching_page",
            "sorting_page",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "communication": (
            "visual_card",
            "help_card",
            "scenario_cards",
            "choice_board",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "transition_self_care": (
            "first_then_board",
            "sequence_cards",
            "choice_board",
            "visual_card",
            "task_analysis_cards",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "emotional_regulation": (
            "emotion_scale",
            "break_card",
            "choice_board",
            "scenario_cards",
            "first_then_board",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "following_directions": (
            "visual_card",
            "first_then_board",
            "sequence_cards",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "social_participation": (
            "social_narrative",
            "scenario_cards",
            "choice_board",
            "visual_card",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "routine_independence": (
            "visual_schedule",
            "task_analysis_cards",
            "first_then_board",
            "choice_board",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "functional_aac": (
            "core_word_board",
            "help_card",
            "choice_board",
            "scenario_cards",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "early_literacy": (
            "visual_card",
            "matching_page",
            "sequence_cards",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "concepts_classification": (
            "sorting_page",
            "matching_page",
            "visual_card",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "play_leisure": (
            "choice_board",
            "scenario_cards",
            "visual_card",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
        "community_safety_vocational": (
            "task_analysis_cards",
            "visual_schedule",
            "scenario_cards",
            "help_card",
            "token_board",
            "data_sheet",
            "summary_template",
        ),
    }

    CATALOG: dict[str, MaterialBlueprint] = {
        "quantity_cards": MaterialBlueprint(
            material_type="quantity_cards",
            display_name="Quantity Cards",
            instructional_purpose=(
                "Teach stable one-to-one correspondence between a numeral and an "
                "exact, countable quantity."
            ),
            required_content=("range", "visualItems", "instruction"),
            professional_rules=(
                "Render every numeral and exact quantity programmatically.",
                "Keep object size and spacing countable without overlap.",
                "Vary theme artwork without changing the mathematical quantity.",
            ),
            teacher_directions=(
                "Present one card at a time before mixing the set.",
                "Accept the teacher-confirmed response mode.",
            ),
        ),
        "number_cards": MaterialBlueprint(
            material_type="number_cards",
            display_name="Number Cards",
            instructional_purpose=(
                "Provide a clean numeral set for recognition, ordering, matching, "
                "and classroom response practice."
            ),
            required_content=("range", "visualItems", "instruction"),
            professional_rules=(
                "Render every numeral programmatically rather than asking an image model to draw it.",
                "Keep one large numeral per card with consistent size and spacing.",
                "Use theme artwork only as a secondary cue that never obscures the numeral.",
            ),
            teacher_directions=(
                "Use the cards for identification, ordering, or numeral-to-quantity matching.",
            ),
        ),
        "matching_page": MaterialBlueprint(
            material_type="matching_page",
            display_name="Matching Practice",
            instructional_purpose=(
                "Provide a concrete discrimination or one-to-one matching activity "
                "aligned to the lesson target."
            ),
            required_content=("pairs", "instruction"),
            professional_rules=(
                "Each source item must have one unambiguous correct match.",
                "Control distractor similarity and include a teacher answer key.",
                "Do not rely on color as the only matching feature.",
            ),
            teacher_directions=(
                "Model one pair, then provide guided and independent opportunities.",
            ),
        ),
        "visual_card": MaterialBlueprint(
            material_type="visual_card",
            display_name="Visual Card",
            instructional_purpose=(
                "Make one action, object, routine, or communication concept quickly "
                "understandable."
            ),
            required_content=("label", "visualItems"),
            professional_rules=(
                "Use one primary concept per card and a brief literal label.",
                "The visual must represent the label directly, not decoratively.",
                "Preserve the teacher-confirmed communication and access mode.",
            ),
            teacher_directions=(
                "Show the card immediately before or during the relevant opportunity.",
            ),
        ),
        "help_card": MaterialBlueprint(
            material_type="help_card",
            display_name="Help Card",
            instructional_purpose=(
                "Give the learner a reliable, accessible way to request assistance."
            ),
            required_content=("requestText", "visualItems"),
            professional_rules=(
                "Support speech, AAC, gesture, sign, pointing, or card exchange.",
                "State the communication partner's expected response.",
                "Never require speech when another response mode was confirmed.",
            ),
            teacher_directions=(
                "Honor the request promptly and model the response without coercion.",
            ),
        ),
        "scenario_cards": MaterialBlueprint(
            material_type="scenario_cards",
            display_name="Scenario Cards",
            instructional_purpose=(
                "Practice the same communication response across familiar situations."
            ),
            required_content=("scenarios", "visualItems"),
            professional_rules=(
                "Keep the target response stable while varying context.",
                "Use concrete, familiar situations without social-value judgments.",
                "Each scenario must have a clear teaching opportunity.",
            ),
            teacher_directions=(
                "Start with the most familiar scenario and generalize gradually.",
            ),
        ),
        "sequence_cards": MaterialBlueprint(
            material_type="sequence_cards",
            display_name="Sequence Cards",
            instructional_purpose=(
                "Represent an event, academic sequence, or routine as an ordered "
                "set of observable steps."
            ),
            required_content=("steps", "visualItems"),
            professional_rules=(
                "Use one observable action or event per card.",
                "Preserve the correct order and render sequence numbers programmatically.",
                "Keep the sequence short enough for the teacher-confirmed target.",
            ),
            teacher_directions=(
                "Model the order, mix only the taught cards, then support sequencing.",
            ),
        ),
        "social_narrative": MaterialBlueprint(
            material_type="social_narrative",
            display_name="Social Situation Guide",
            instructional_purpose=(
                "Explain a familiar social situation, available responses, and "
                "support options without prescribing thoughts or emotions."
            ),
            required_content=("situation", "responseOptions", "supportOptions"),
            professional_rules=(
                "Use neutral first- or third-person factual language.",
                "Describe multiple acceptable responses instead of one compliance script.",
                "Do not claim to know what another person thinks or how the learner feels.",
            ),
            teacher_directions=(
                "Preview before the situation and revise wording with learner or team input.",
            ),
        ),
        "core_word_board": MaterialBlueprint(
            material_type="core_word_board",
            display_name="Core Word Communication Board",
            instructional_purpose=(
                "Keep a small set of high-utility messages available across lesson "
                "activities and communication partners."
            ),
            required_content=("words", "responseModes", "visualItems"),
            professional_rules=(
                "Use teacher-confirmed vocabulary, symbols, language, and access method.",
                "Keep symbol and word positions stable across uses.",
                "Include rejecting, stopping, helping, and choosing—not only compliance words.",
            ),
            teacher_directions=(
                "Model messages without requiring imitation and honor all intentional responses.",
            ),
        ),
        "first_then_board": MaterialBlueprint(
            material_type="first_then_board",
            display_name="First–Then Board",
            instructional_purpose=(
                "Clarify a short sequence and support predictable movement between "
                "two activities."
            ),
            required_content=("firstText", "thenText", "visualItems"),
            professional_rules=(
                "The first step must be concrete, attainable, and brief.",
                "The then item must be genuinely available and teacher-confirmed.",
                "Do not present First–Then as a threat or forced-compliance tool.",
            ),
            teacher_directions=(
                "Preview both steps, mark First complete, then transition to Then.",
            ),
        ),
        "choice_board": MaterialBlueprint(
            material_type="choice_board",
            display_name="Choice Board",
            instructional_purpose=(
                "Offer meaningful, available options in an accessible visual format."
            ),
            required_content=("options", "visualItems"),
            professional_rules=(
                "Offer two to four real choices with equal visual prominence.",
                "Remove unavailable choices before presenting the board.",
                "Provide an accessible way to indicate a selection.",
            ),
            teacher_directions=(
                "Honor the selected available choice or explain a change neutrally.",
            ),
        ),
        "token_board": MaterialBlueprint(
            material_type="token_board",
            display_name="Reinforcement Board",
            instructional_purpose=(
                "Make progress toward a confirmed reinforcer visible and predictable."
            ),
            required_content=("tokenCount", "rewardLabel"),
            professional_rules=(
                "Use a brief attainable token requirement.",
                "Name a teacher-confirmed, currently available reinforcer.",
                "Do not use deprivation, loss threats, or response-cost by default.",
            ),
            teacher_directions=(
                "Deliver each token promptly and pair it with specific positive feedback.",
            ),
        ),
        "data_sheet": MaterialBlueprint(
            material_type="data_sheet",
            display_name="Data Sheet",
            instructional_purpose=(
                "Record the observable target, independence, and support used without "
                "reducing progress to correctness alone."
            ),
            required_content=("columns", "summaryCalculation"),
            professional_rules=(
                "Match each row to a defined teaching opportunity.",
                "Separate independent, prompted, incorrect, and no-response outcomes.",
                "Include prompt level and a brief notes field when relevant.",
            ),
            teacher_directions=(
                "Record during or immediately after each planned opportunity.",
            ),
        ),
        "summary_template": MaterialBlueprint(
            material_type="summary_template",
            display_name="Lesson Summary",
            instructional_purpose=(
                "Capture what worked, support used, small wins, and the next teaching step."
            ),
            required_content=("prompts",),
            professional_rules=(
                "Keep prompts brief enough to complete after instruction.",
                "Include independence, engagement, and next-step reflection.",
            ),
            teacher_directions=("Complete after the lesson while details are fresh.",),
        ),
        "break_card": MaterialBlueprint(
            material_type="break_card",
            display_name="Break Card",
            instructional_purpose="Support an accessible break request and predictable return.",
            required_content=("requestText", "returnCue"),
            professional_rules=(
                "Honor the communication function.",
                "Use a neutral return cue without forced compliance.",
            ),
            teacher_directions=("Teach both requesting a break and returning with support.",),
        ),
        "visual_schedule": MaterialBlueprint(
            material_type="visual_schedule",
            display_name="Visual Schedule",
            instructional_purpose=(
                "Show an ordered routine and make completed steps visibly predictable."
            ),
            required_content=("steps", "completionCue", "visualItems"),
            professional_rules=(
                "Use concrete observable steps in the correct order.",
                "Keep the current step easy to identify and include a Done state.",
                "Do not expose private learner information on the schedule.",
            ),
            teacher_directions=(
                "Preview the schedule, reference the current step, and mark completion.",
            ),
        ),
        "task_analysis_cards": MaterialBlueprint(
            material_type="task_analysis_cards",
            display_name="Task Analysis Cards",
            instructional_purpose=(
                "Break a functional routine into teachable, observable steps."
            ),
            required_content=("steps", "visualItems"),
            professional_rules=(
                "Use safe, observable steps in a logical sequence.",
                "Keep each card to one action and preserve chronological-age dignity.",
                "Teacher review is required for safety-sensitive self-care routines.",
            ),
            teacher_directions=(
                "Teach and prompt only the steps selected by the learner's team.",
            ),
        ),
        "emotion_scale": MaterialBlueprint(
            material_type="emotion_scale",
            display_name="Emotion & Regulation Scale",
            instructional_purpose=(
                "Support communication about internal state and available regulation options."
            ),
            required_content=("levels", "regulationOptions", "visualItems"),
            professional_rules=(
                "Use neutral nonjudgmental labels rather than good/bad behavior.",
                "Offer accessible communication and regulation options.",
                "Do not infer an internal state solely from appearance.",
            ),
            teacher_directions=(
                "Invite, never force, self-identification and honor communication differences.",
            ),
        ),
        "sorting_page": MaterialBlueprint(
            material_type="sorting_page",
            display_name="Sorting Practice",
            instructional_purpose="Practice classification using visible defining features.",
            required_content=("categories", "items"),
            professional_rules=(
                "Define mutually understandable categories.",
                "Include an answer key and avoid ambiguous items.",
            ),
            teacher_directions=("Model the category rule before independent sorting.",),
        ),
        "teacher_cue_card": MaterialBlueprint(
            material_type="teacher_cue_card",
            display_name="Teacher Cue Card",
            instructional_purpose="Keep the teaching sequence concise and consistent.",
            required_content=("cueSteps",),
            professional_rules=(
                "Include opportunity, wait time, prompting, feedback, and data cue.",
                "Keep learner-private context off the printed classroom-facing side.",
            ),
            teacher_directions=("Use as a quick reference, not as a rigid script.",),
        ),
        "session_summary": MaterialBlueprint(
            material_type="session_summary",
            display_name="Session Summary",
            instructional_purpose="Summarize implementation and learner response.",
            required_content=("prompts",),
            professional_rules=("Separate observation from interpretation.",),
            teacher_directions=("Record concise, observable notes.",),
        ),
        "handoff_note": MaterialBlueprint(
            material_type="handoff_note",
            display_name="Handoff Note",
            instructional_purpose="Share approved implementation details with an authorized team.",
            required_content=("fields",),
            professional_rules=("Include only approved, necessary educational information.",),
            teacher_directions=("Review authorization and audience before sharing.",),
        ),
    }

    @classmethod
    def classify_goal(cls, draft: LessonDesignDraftDto) -> str:
        primary_text = " ".join(
            [draft.goalText, draft.observableResponse, draft.theme]
        ).casefold()
        # Scenarios describe where a skill is practised, not what the skill is.
        # Classifying from them caused concrete objects such as toys, buses, or
        # sorting materials to override the teacher-confirmed instructional goal.
        text = primary_text
        if any(
            term in text
            for term in (
                "count",
                "number",
                "quantity",
                "cardinality",
                "数数",
                "数量",
            )
        ):
            return "counting"
        if any(
            term in text
            for term in (
                "emotion",
                "feeling",
                "regulation",
                "calm",
                "coping",
                "break request",
                "情绪",
                "调节",
                "冷静",
                "休息请求",
            )
        ):
            return "emotional_regulation"
        if any(
            term in text
            for term in (
                "core word",
                "yes/no",
                "yes no",
                "comment",
                "protest",
                "拒绝",
                "核心词",
            )
        ):
            return "functional_aac"
        if any(
            term in text
            for term in (
                "social",
                "turn taking",
                "turn-taking",
                "peer",
                "sharing",
                "join play",
                "conversation turn",
                "社交",
                "轮流",
                "同伴",
                "分享",
            )
        ):
            return "social_participation"
        if any(
            term in text
            for term in (
                "safety",
                "community",
                "crossing",
                "bus",
                "work task",
                "vocational",
                "job",
                "社区",
                "安全",
                "职业",
                "工作技能",
            )
        ):
            return "community_safety_vocational"
        if any(
            term in text
            for term in (
                "transition",
                "self-care",
                "self care",
                "toileting",
                "dressing",
                "washing",
                "brushing",
                "过渡",
                "自理",
            )
        ):
            return "transition_self_care"
        if any(
            term in text
            for term in (
                "routine",
                "independent work",
                "task completion",
                "work system",
                "schedule",
                "morning routine",
                "课堂常规",
                "独立完成",
                "日程",
            )
        ):
            return "routine_independence"
        if any(
            term in text
            for term in (
                "follow direction",
                "following direction",
                "one-step direction",
                "two-step direction",
                "receptive language",
                "listener responding",
                "遵循指令",
                "听从指令",
                "接受性语言",
            )
        ):
            return "following_directions"
        if any(
            term in text
            for term in (
                "letter",
                "phonics",
                "sound out",
                "sight word",
                "read",
                "story sequence",
                "comprehension",
                "识字",
                "字母",
                "阅读",
                "拼读",
            )
        ):
            return "early_literacy"
        if any(
            term in text
            for term in (
                "sort",
                "classify",
                "category",
                "match by",
                "same and different",
                "分类",
                "归类",
                "配对",
            )
        ):
            return "concepts_classification"
        if any(
            term in primary_text
            for term in (
                "play",
                "leisure",
                "game",
                "toy",
                "recreation",
                "游戏",
                "玩耍",
                "休闲",
            )
        ):
            return "play_leisure"
        if any(
            term in text
            for term in (
                "ask for help",
                "request",
                "communicat",
                "aac",
                "conversation",
                "沟通",
                "请求",
            )
        ):
            return "communication"
        return "general"

    @classmethod
    def recommended_bundle(cls, draft: LessonDesignDraftDto) -> list[str]:
        family = cls.classify_goal(draft)
        if family in cls.CORE_BUNDLES:
            return list(cls.CORE_BUNDLES[family])

        return [
            "visual_card",
            "scenario_cards",
            "token_board",
            "data_sheet",
            "summary_template",
        ]

    @classmethod
    def blueprint(cls, material_type: str) -> MaterialBlueprint | None:
        return cls.CATALOG.get(material_type)

    @classmethod
    def missing_from_bundle(
        cls, draft: LessonDesignDraftDto, material_types: Iterable[str]
    ) -> list[str]:
        required = set(cls.recommended_bundle(draft))
        return sorted(required.difference(material_types))
