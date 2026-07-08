from __future__ import annotations

from copy import deepcopy

from app.integrations.ai_provider import V2AIProvider
from app.schemas.v2_dto import (
    AIQuestion,
    AIQuestionOption,
    LearnerProfile,
    LearnerRecord,
    LessonDesignDraft,
    LessonDesignDraftDto,
)


def _option(
    option_id: str, label: str, icon: str, recommended: bool = False
) -> AIQuestionOption:
    return AIQuestionOption(
        id=option_id,
        label=label,
        value=label,
        icon=icon,
        recommended=recommended,
        source="ai_generated",
    )


class MockV2AIProvider(V2AIProvider):
    """Deterministic provider used until a real safeguarded provider is configured."""

    def extract_profile(
        self, learner: LearnerProfile, records: list[LearnerRecord]
    ) -> tuple[LearnerProfile, list[str]]:
        extracted = learner.model_copy(deep=True)
        if records and not extracted.support_needs:
            extracted.support_needs = ["Visual prompts", "Short attention span"]
        return extracted, [
            "Use visual supports",
            "Keep activities short",
            "Add multiple examples",
        ]

    def generate_lesson_questions(
        self, learner: LearnerProfile, teacher_request: str
    ) -> tuple[list[AIQuestion], LessonDesignDraft]:
        questions = [
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
                    _option("toy-car", "Toy car stuck", "🚙", True),
                    _option("closed-box", "Closed box", "▣", True),
                    _option("backpack", "Backpack zipper", "🎒", True),
                    _option("snack-container", "Snack container", "🥨"),
                    _option("puzzle-piece", "Puzzle piece missing", "🧩"),
                ],
                selected_option_ids=["toy-car", "closed-box", "backpack"],
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
                selected_option_ids=["visual-cards", "help-card", "token-board", "data-sheet", "summary"],
                allow_custom_answer=True,
                max_selections=5,
            ),
            AIQuestion(
                id="reinforcer",
                prompt="What is most likely to motivate participation today?",
                helper_text="Choose one or two preferences. You remain in control of reinforcement.",
                field="customNotes",
                input_type="hybrid",
                options=[
                    _option("car-play", "Car play", "🚗", True),
                    _option("reinforcer-token", "Token board", "⭐", True),
                    _option("bubbles", "Bubbles", "🫧"),
                    _option("music-break", "Music break", "🎵"),
                    _option("teacher-praise", "Teacher praise", "👏"),
                ],
                selected_option_ids=["car-play", "reinforcer-token"],
                allow_custom_answer=True,
                max_selections=2,
            ),
            AIQuestion(
                id="prompting-strategy",
                prompt="How should prompting be introduced and faded?",
                helper_text="Select strategies that preserve wait time and support independence.",
                field="customNotes",
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
        ]
        asks_for_help = "ask for help" in teacher_request.lower() or "asking for help" in teacher_request.lower()
        draft = LessonDesignDraft(
            id=f"draft-{learner.id}",
            learner_id=learner.id,
            goal_text=(
                "Learner will ask for help using a short phrase."
                if asks_for_help
                else "Learner will practice the requested skill with teacher support."
            ),
            response_level="Short phrase",
            scenarios=["Toy car stuck", "Closed box", "Backpack zipper"],
            selected_materials=["Visual Cards", "Help Card", "Token Board", "Data Sheet", "Summary Template"],
            theme="Vehicles",
            duration="10–12 min",
            custom_notes=(
                "Reinforcers: Car play, Token board. Prompting: Visual prompt first, Least-to-most prompting."
                if asks_for_help
                else f"Teacher request: {teacher_request} Reinforcers: Car play, Token board. Prompting: Visual prompt first, Least-to-most prompting."
            ),
        )
        return deepcopy(questions), draft

    def polish_lesson_brief(self, draft: LessonDesignDraft) -> str:
        return "Practice the target skill across short, familiar situations with teacher-confirmed supports."

    def generate_lesson_package(self, draft: LessonDesignDraftDto) -> dict:
        """Deterministic fake content behind the same boundary a real model will use."""

        return {
            "lessonBrief": (
                "Teach the learner to ask for help using a short phrase across familiar, "
                "vehicle-themed practice situations. Begin with visual support and wait "
                "time, use least-to-most prompting, reinforce participation with car play "
                "and tokens, and record independence, prompt level, engagement, and regulation."
            ),
            "summaryTemplate": (
                "Record what worked, what support was needed, the learner’s smallest win, "
                "and the next step for independence, prompt fading, participation, or generalization."
            ),
        }

    def generate_material_image(
        self,
        learner: LearnerProfile,
        material_type: str,
        prompt: str,
        style: str | None = None,
        size: str | None = None,
    ) -> dict:
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
