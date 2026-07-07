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
                prompt="What level of response should we target?",
                helper_text="Choose an achievable communication level.",
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
                prompt="Which scenarios would you like to include?",
                helper_text="Select familiar practice opportunities.",
                field="scenarios",
                input_type="multi_select",
                options=[
                    _option("toy-car", "Toy car stuck", "🚙", True),
                    _option("closed-box", "Closed box", "▣", True),
                    _option("backpack", "Backpack zipper", "🎒"),
                ],
                selected_option_ids=["toy-car", "closed-box"],
                allow_custom_answer=True,
                max_selections=3,
            ),
            AIQuestion(
                id="materials",
                prompt="Which materials would you like to use?",
                helper_text="Select supports for prompting, reinforcement, and data.",
                field="selectedMaterials",
                input_type="hybrid",
                options=[
                    _option("visual-cards", "Visual Cards", "▧", True),
                    _option("token-board", "Token Board", "☆", True),
                    _option("data-sheet", "Data Sheet", "▦", True),
                    _option("summary", "Summary Template", "▤"),
                ],
                selected_option_ids=["visual-cards", "token-board", "data-sheet"],
                allow_custom_answer=True,
                max_selections=4,
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
            scenarios=["Toy car stuck", "Closed box"],
            selected_materials=["Visual Cards", "Token Board", "Data Sheet"],
            theme="Vehicles",
            duration="10–12 min",
            custom_notes="" if asks_for_help else teacher_request,
        )
        return deepcopy(questions), draft

    def polish_lesson_brief(self, draft: LessonDesignDraft) -> str:
        return "Practice the target skill across short, familiar situations with teacher-confirmed supports."

    def generate_lesson_package(self, draft: LessonDesignDraftDto) -> dict:
        """Deterministic fake content behind the same boundary a real model will use."""

        return {
            "lessonBrief": (
                f"Teach {draft.goalText.lower()} through short, structured practice "
                "with visual prompts, prompt fading, and positive reinforcement."
            ),
            "summaryTemplate": (
                "Record participation, prompt level, independence, regulation, "
                "generalization attempts, and the next small step."
            ),
        }
