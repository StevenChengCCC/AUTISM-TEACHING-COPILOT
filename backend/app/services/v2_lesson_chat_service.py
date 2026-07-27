from __future__ import annotations

from app.core.exceptions import NotFoundError, ValidationError
from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.schemas.v2_dto import (
    AIChatState,
    AIChatStateDto,
    AIMessage,
    AIQuestion,
    AIQuestionOption,
    GenerationMetadataDto,
    LessonDesignDraft,
    QuestionAnswerUpdate,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_repositories import V2Repositories, repositories


class V2LessonChatService:
    core_question_fields = (
        "goalText",
        "baseline",
        "responseLevel",
        "scenarios",
        "selectedMaterials",
    )
    printable_material_options = [
        AIQuestionOption(
            id="visual-cards",
            label="Visual Cards",
            value="Visual Cards",
            description="Printable visual examples tailored to the lesson goal.",
            icon="▧",
            recommended=True,
        ),
        AIQuestionOption(
            id="help-card",
            label="Help Card",
            value="Help Card",
            description="A concise printable communication support.",
            icon="💬",
        ),
        AIQuestionOption(
            id="token-board",
            label="Token Board",
            value="Token Board",
            description="An optional printable participation support.",
            icon="☆",
        ),
        AIQuestionOption(
            id="data-sheet",
            label="Data Sheet",
            value="Data Sheet",
            description="Tracks independence, prompting, participation, and response.",
            icon="▦",
            recommended=True,
        ),
        AIQuestionOption(
            id="summary-template",
            label="Summary Template",
            value="Summary Template",
            description="A printable teacher reflection and next-steps page.",
            icon="▤",
            recommended=True,
        ),
    ]
    greeting = (
        "Tell me what you want to teach today, and I’ll help turn it into a lesson kit."
    )

    def __init__(
        self, repos: V2Repositories = repositories, ai: V2AIProvider | None = None
    ):
        self.repos = repos
        self.learners = V2LearnerService(repos)
        self.ai = ai or get_v2_ai_provider()

    def start(
        self, learner_id: str, *, resume_existing: bool = False
    ) -> AIChatState:
        self.learners.get(learner_id)
        conversation_id = f"conversation-{learner_id}"
        existing = self.repos.chats.get(conversation_id)
        if resume_existing and existing is not None:
            existing.questions = self._prepare_questions(
                existing.questions, require_fresh_confirmation=False
            )
            existing.draft = self._prepare_draft(existing.draft)
            existing.can_generate = bool(existing.questions) and all(
                self._answered(item) for item in existing.questions
            )
            return self.repos.chats.save(existing)
        chat = AIChatState(
            conversation_id=conversation_id,
            learner_id=learner_id,
            messages=[
                AIMessage(
                    id=self.repos.next_id("message"),
                    role="assistant",
                    content=self.greeting,
                )
            ],
            questions=[],
            draft=LessonDesignDraft(id=f"draft-{learner_id}", learner_id=learner_id),
            can_generate=False,
        )
        return self.repos.chats.save(chat)

    def start_dto(
        self, learner_id: str, *, resume_existing: bool = False
    ) -> AIChatStateDto:
        return self.to_dto(
            self.start(learner_id, resume_existing=resume_existing)
        )

    def submit_request(self, conversation_id: str, content: str) -> AIChatState:
        chat = self._get(conversation_id)
        clean = content.strip()
        if not clean:
            raise ValidationError("Lesson request cannot be empty")
        chat.messages.append(
            AIMessage(id=self.repos.next_id("message"), role="teacher", content=clean)
        )
        if not chat.questions:
            learner = self.learners.get(chat.learner_id)
            questions, draft = self.ai.generate_lesson_questions(learner, clean)
            draft.id = chat.draft.id
            chat.questions = self._prepare_questions(
                questions, require_fresh_confirmation=True
            )
            chat.draft = self._prepare_draft(draft)
            metadata = getattr(self.ai, "last_generation_metadata", None)
            if metadata is not None:
                chat.generation_status = metadata.status
                chat.generation_metadata = GenerationMetadataDto.model_validate(
                    metadata.model_dump(mode="json", by_alias=True)
                )
            response = "Great. I’ll ask a few quick questions so we can generate the right teaching materials."
        else:
            chat.draft.custom_notes = " ".join(
                filter(None, [chat.draft.custom_notes, clean])
            )
            response = "Thanks. I’ve kept your lesson choices and added that note to the draft."
        chat.messages.append(
            AIMessage(
                id=self.repos.next_id("message"), role="assistant", content=response
            )
        )
        chat.can_generate = bool(chat.questions) and all(
            self._answered(item) for item in chat.questions
        )
        return self.repos.chats.save(chat)

    def submit_message_dto(
        self, conversation_id: str, learner_id: str, content: str
    ) -> AIChatStateDto:
        chat = self._get(conversation_id)
        if chat.learner_id != learner_id:
            raise ValidationError("Conversation does not belong to this learner")
        return self.to_dto(self.submit_request(conversation_id, content))

    def update_answer(
        self, conversation_id: str, question_id: str, payload: QuestionAnswerUpdate
    ) -> AIChatState:
        chat = self._get(conversation_id)
        question = next(
            (item for item in chat.questions if item.id == question_id), None
        )
        if not question:
            raise NotFoundError("AI question not found")
        selected = [
            item
            for item in payload.selected_option_ids
            if any(option.id == item for option in question.options)
        ]
        if question.input_type == "single_select":
            selected = selected[-1:]
        elif question.max_selections is not None:
            selected = selected[: question.max_selections]
        question.options = [
            option for option in question.options if option.source != "teacher_custom"
        ]
        question.custom_answer = payload.custom_answer.strip()
        if question.custom_answer:
            custom_id = f"custom-{question.id}"
            question.options.append(
                AIQuestionOption(
                    id=custom_id,
                    label=question.custom_answer,
                    value=question.custom_answer,
                    icon="✎",
                    source="teacher_custom",
                )
            )
            selected = (
                [custom_id]
                if question.input_type == "single_select"
                else [*selected, custom_id]
            )
        question.selected_option_ids = selected
        self._apply_answer(chat.draft, question)
        if question.field == "customNotes":
            self._apply_custom_notes(chat.draft, chat.questions)
        chat.can_generate = all(self._answered(item) for item in chat.questions)
        return self.repos.chats.save(chat)

    def update_answer_dto(
        self,
        conversation_id: str,
        question_id: str,
        payload: QuestionAnswerUpdate,
    ) -> AIChatStateDto:
        return self.to_dto(self.update_answer(conversation_id, question_id, payload))

    def clear(self, conversation_id: str) -> AIChatState:
        chat = self._get(conversation_id)
        chat.messages = [
            AIMessage(
                id=self.repos.next_id("message"),
                role="assistant",
                content=self.greeting,
            )
        ]
        chat.can_generate = bool(chat.questions) and all(
            self._answered(question) for question in chat.questions
        )
        chat.generation_status = None
        chat.generation_metadata = None
        return self.repos.chats.save(chat)

    def clear_dto(self, conversation_id: str) -> AIChatStateDto:
        return self.to_dto(self.clear(conversation_id))

    def get(self, conversation_id: str) -> AIChatState:
        return self._get(conversation_id)

    def _get(self, conversation_id: str) -> AIChatState:
        chat = self.repos.chats.get(conversation_id)
        if not chat:
            raise NotFoundError("Lesson chat not found")
        return chat

    @staticmethod
    def to_dto(chat: AIChatState) -> AIChatStateDto:
        return AIChatStateDto.model_validate(
            chat.model_dump(mode="json", by_alias=True)
        )

    @staticmethod
    def _answered(question: AIQuestion) -> bool:
        return not question.required or bool(
            question.selected_option_ids or question.custom_answer.strip()
        )

    @classmethod
    def _prepare_questions(
        cls,
        questions: list[AIQuestion],
        *,
        require_fresh_confirmation: bool,
    ) -> list[AIQuestion]:
        """Keep the teacher-facing conversation short, safe, and printable-first."""

        by_field: dict[str, AIQuestion] = {}
        for question in questions:
            if question.field not in cls.core_question_fields:
                continue
            if question.field in by_field:
                continue
            by_field[question.field] = cls._prepare_question(
                question,
                require_fresh_confirmation=require_fresh_confirmation,
            )
        return [
            by_field[field]
            for field in cls.core_question_fields
            if field in by_field
        ][:5]

    @classmethod
    def _prepare_question(
        cls,
        question: AIQuestion,
        *,
        require_fresh_confirmation: bool,
    ) -> AIQuestion:
        if question.field == "selectedMaterials":
            return question.model_copy(
                update={
                    "prompt": "Which printable materials should be included in the lesson kit?",
                    "helper_text": (
                        "Select only the classroom pages you want to review and print. "
                        "Digital apps are not included automatically."
                    ),
                    "input_type": "multi_select",
                    "options": [
                        option.model_copy(deep=True)
                        for option in cls.printable_material_options
                    ],
                    "selected_option_ids": (
                        []
                        if require_fresh_confirmation
                        else [
                            item
                            for item in question.selected_option_ids
                            if item
                            in {
                                option.id
                                for option in cls.printable_material_options
                            }
                        ]
                    ),
                    "custom_answer": "",
                    "allow_custom_answer": True,
                    "required": True,
                    "max_selections": 5,
                }
            )

        options: list[AIQuestionOption] = []
        selected_ids = set(question.selected_option_ids)
        for option in question.options:
            normalized = option.label.casefold()
            if "full physical" in normalized or "hand-over-hand" in normalized:
                selected_ids.discard(option.id)
                continue
            options.append(
                option.model_copy(
                    update={
                        "source": "ai_generated",
                        "recommended": bool(option.recommended),
                    }
                )
            )

        custom_answer = question.custom_answer.strip()
        if custom_answer and require_fresh_confirmation:
            suggestion_id = f"suggested-{question.id}"
            options.insert(
                0,
                AIQuestionOption(
                    id=suggestion_id,
                    label=custom_answer,
                    value=custom_answer,
                    description="AI suggestion — teacher confirmation required.",
                    icon="✦",
                    recommended=True,
                ),
            )
            custom_answer = ""

        return question.model_copy(
            update={
                "options": options,
                "selected_option_ids": (
                    [] if require_fresh_confirmation else list(selected_ids)
                ),
                "custom_answer": custom_answer,
                "helper_text": question.helper_text
                or "Review the suggestion and confirm or edit it before generation.",
            }
        )

    @staticmethod
    def _prepare_draft(draft: LessonDesignDraft) -> LessonDesignDraft:
        material_aliases = {
            "manipulatives": "Visual Cards",
            "counting manipulatives": "Visual Cards",
            "visual card": "Visual Cards",
            "visual cards": "Visual Cards",
            "visual cues": "Visual Cards",
            "visual_cues": "Visual Cards",
            "visual number cards": "Visual Cards",
            "number cards": "Visual Cards",
            "number cards 1 to 5": "Visual Cards",
            "help card": "Help Card",
            "token board": "Token Board",
            "data sheet": "Data Sheet",
            "tally sheet": "Data Sheet",
            "summary template": "Summary Template",
        }
        materials: list[str] = []
        for item in draft.selected_materials:
            normalized = item.replace("-", " ").replace("_", " ").strip().casefold()
            mapped = material_aliases.get(normalized)
            if mapped and mapped not in materials:
                materials.append(mapped)
        if not materials:
            materials = ["Visual Cards", "Data Sheet", "Summary Template"]

        prompting_start = draft.prompting_start
        if any(
            term in prompting_start.casefold()
            for term in ("full physical", "hand-over-hand")
        ):
            prompting_start = (
                "Wait, then use visual, gestural, or verbal least-to-most support"
            )
        return draft.model_copy(
            update={
                "selected_materials": materials,
                "prompting_start": prompting_start,
            }
        )

    @staticmethod
    def _apply_answer(draft: LessonDesignDraft, question: AIQuestion) -> None:
        values = [
            option.value
            for option in question.options
            if option.id in question.selected_option_ids
        ]
        first = values[0] if values else ""
        joined = ", ".join(values)
        if question.field == "goalText":
            draft.goal_text = first
            draft.observable_response = first
        elif question.field == "baseline":
            draft.baseline = first
        elif question.field == "responseLevel":
            draft.response_level = values[0] if values else ""
            if "ask for help" in draft.goal_text.lower() and draft.response_level:
                draft.goal_text = (
                    f"Learner will ask for help using a {draft.response_level.lower()}."
                )
        elif question.field == "scenarios":
            draft.scenarios = values
        elif question.field == "selectedMaterials":
            draft.selected_materials = values
        elif question.field == "opportunities":
            digits = "".join(character for character in first if character.isdigit())
            if digits:
                draft.opportunities = max(1, min(50, int(digits)))
        elif question.field == "duration":
            draft.duration = first
        elif question.field == "promptingStart":
            draft.prompting_start = joined
        elif question.field == "promptingLimits":
            draft.prompting_limits = joined
        elif question.field == "reinforcementPlan":
            draft.reinforcement_plan = joined
        elif question.field == "errorCorrection":
            draft.error_correction = joined
        elif question.field == "dataCollection":
            draft.data_collection = joined
        elif question.field == "generalizationPlan":
            draft.generalization_plan = joined
        elif question.field == "teacherConstraints":
            draft.teacher_constraints = joined

    @staticmethod
    def _apply_custom_notes(
        draft: LessonDesignDraft, questions: list[AIQuestion]
    ) -> None:
        note_groups: list[str] = []
        labels = {
            "reinforcer": "Reinforcers",
            "prompting-strategy": "Prompting",
        }
        for question in questions:
            if question.field != "customNotes":
                continue
            values = [
                option.value
                for option in question.options
                if option.id in question.selected_option_ids
            ]
            if values:
                note_groups.append(
                    f"{labels.get(question.id, 'Teacher notes')}: {', '.join(values)}."
                )
        draft.custom_notes = " ".join(note_groups)
