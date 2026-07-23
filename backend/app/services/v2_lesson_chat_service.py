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
            return existing
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
            chat.questions = questions
            chat.draft = draft
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
