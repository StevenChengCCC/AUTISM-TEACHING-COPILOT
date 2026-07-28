from __future__ import annotations

import re

from app.core.exceptions import NotFoundError, ValidationError, VersionConflictError
from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.schemas.v2_dto import (
    AIChatState,
    AIChatStateDto,
    AIMessage,
    AIQuestion,
    AIQuestionOption,
    GenerationMetadataDto,
    LessonDesignDraft,
    LessonDesignDraftDto,
    QuestionAnswerUpdate,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_material_blueprint_service import V2MaterialBlueprintService
from app.services.v2_repositories import V2Repositories, repositories


class V2LessonChatService:
    core_question_fields = (
        "goalText",
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
    cancellation_message = (
        "That request was canceled. Tell me the corrected teaching goal when you’re ready."
    )

    def __init__(
        self, repos: V2Repositories = repositories, ai: V2AIProvider | None = None
    ):
        self.repos = repos
        self.learners = V2LearnerService(repos)
        self.ai = ai or get_v2_ai_provider()

    def start(self, learner_id: str, *, resume_existing: bool = False) -> AIChatState:
        self.learners.get(learner_id)
        conversation_id = f"conversation-{learner_id}"
        existing = self.repos.chats.get(conversation_id)
        if resume_existing and existing is not None:
            questions = self._prepare_questions(
                existing.questions,
                require_fresh_confirmation=False,
                draft=existing.draft,
            )
            return existing.model_copy(
                update={
                    "questions": questions,
                    "draft": self._prepare_draft(existing.draft),
                    "can_generate": bool(questions)
                    and all(self._answered(item) for item in questions),
                }
            )
        draft_version = existing.draft.version if existing is not None else 1
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
            draft=LessonDesignDraft(
                id=f"draft-{learner_id}",
                learner_id=learner_id,
                version=draft_version,
            ),
            can_generate=False,
        )
        for attempt in range(2):
            try:
                return self.repos.chats.save(chat)
            except VersionConflictError:
                if attempt:
                    raise
                latest = self.repos.chats.get(conversation_id)
                if latest is None:
                    raise
                chat.draft.version = latest.draft.version
        return chat

    def start_dto(
        self, learner_id: str, *, resume_existing: bool = False
    ) -> AIChatStateDto:
        return self.to_dto(self.start(learner_id, resume_existing=resume_existing))

    def submit_request(self, conversation_id: str, content: str) -> AIChatState:
        clean = content.strip()
        if not clean:
            raise ValidationError("Lesson request cannot be empty")
        self._validate_request_specificity(clean)

        initial = self._get(conversation_id)
        generated: tuple[list[AIQuestion], LessonDesignDraft] | None = None
        generation_metadata = None
        if not initial.questions:
            learner = self.learners.get(initial.learner_id)
            questions, draft = self.ai.generate_lesson_questions(learner, clean)
            generated = (questions, draft)
            generation_metadata = getattr(self.ai, "last_generation_metadata", None)

        # OpenAI generation can take several seconds. During that time a duplicate
        # browser request or another tab may advance the draft version. Re-load and
        # merge on conflict so an implementation detail never becomes a teacher
        # facing "refresh and try again" error.
        for attempt in range(3):
            chat = initial if attempt == 0 else self._get(conversation_id)
            if attempt and self._request_was_cancelled(chat):
                return chat
            if self._request_already_applied(chat, clean):
                return chat
            chat = self._apply_request(
                chat,
                clean,
                generated=generated,
                generation_metadata=generation_metadata,
            )
            try:
                return self.repos.chats.save(chat)
            except VersionConflictError:
                if attempt == 2:
                    raise VersionConflictError(
                        "We could not save the lesson suggestions. Please try once more."
                    )
        raise VersionConflictError(
            "We could not save the lesson suggestions. Please try once more."
        )

    def _apply_request(
        self,
        chat: AIChatState,
        clean: str,
        *,
        generated: tuple[list[AIQuestion], LessonDesignDraft] | None,
        generation_metadata,
    ) -> AIChatState:
        chat.messages.append(
            AIMessage(id=self.repos.next_id("message"), role="teacher", content=clean)
        )
        if not chat.questions and generated is not None:
            questions, generated_draft = generated
            draft = generated_draft.model_copy(
                update={
                    "id": chat.draft.id,
                    "learner_id": chat.learner_id,
                    "version": chat.draft.version,
                },
                deep=True,
            )
            chat.questions = self._prepare_questions(
                questions,
                require_fresh_confirmation=True,
                draft=draft,
            )
            chat.draft = self._prepare_draft(draft)
            if generation_metadata is not None:
                chat.generation_status = generation_metadata.status
                chat.generation_metadata = GenerationMetadataDto.model_validate(
                    generation_metadata.model_dump(mode="json", by_alias=True)
                )
            response = (
                "I’ve turned that request into three suggested lesson choices. "
                "Pick what fits your learner."
            )
        else:
            chat.questions = self._prepare_questions(
                chat.questions,
                require_fresh_confirmation=False,
                draft=chat.draft,
            )
            chat.draft = self._prepare_draft(chat.draft)
            chat.draft.custom_notes = " ".join(
                filter(None, [chat.draft.custom_notes, clean])
            )
            response = "Thanks. I’ve kept your choices and added that note."
        chat.messages.append(
            AIMessage(
                id=self.repos.next_id("message"), role="assistant", content=response
            )
        )
        chat.can_generate = bool(chat.questions) and all(
            self._answered(item) for item in chat.questions
        )
        return chat

    @staticmethod
    def _request_already_applied(chat: AIChatState, clean: str) -> bool:
        return bool(chat.questions) and any(
            message.role == "teacher" and message.content.strip() == clean
            for message in chat.messages
        )

    @classmethod
    def _request_was_cancelled(cls, chat: AIChatState) -> bool:
        return any(
            message.role == "assistant"
            and message.content == cls.cancellation_message
            for message in chat.messages
        )

    @staticmethod
    def _validate_request_specificity(clean: str) -> None:
        words = re.findall(r"\w+", clean.casefold(), flags=re.UNICODE)
        generic_words = {
            "a",
            "an",
            "the",
            "i",
            "me",
            "my",
            "him",
            "her",
            "child",
            "kid",
            "learner",
            "student",
            "want",
            "need",
            "please",
            "help",
            "teach",
            "teaching",
            "lesson",
            "make",
            "create",
            "generate",
            "build",
            "to",
        }
        meaningful = [word for word in words if word not in generic_words]
        vague_phrases = {
            "教",
            "教学",
            "帮我",
            "做课程",
            "生成课程",
            "上课",
        }
        if not meaningful or clean.casefold() in vague_phrases:
            raise ValidationError(
                "Please add the skill to teach, for example: "
                "“Teach identifying fruit” or “Teach asking for help.”"
            )

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
        for attempt in range(2):
            chat = self._get(conversation_id)
            chat.questions = self._prepare_questions(
                chat.questions,
                require_fresh_confirmation=False,
                draft=chat.draft,
            )
            chat.draft = self._prepare_draft(chat.draft)
            try:
                return self._update_answer(chat, question_id, payload)
            except VersionConflictError:
                if attempt:
                    raise
        raise VersionConflictError(
            "The lesson draft changed after it was loaded. Refresh and try again."
        )

    def _update_answer(
        self,
        chat: AIChatState,
        question_id: str,
        payload: QuestionAnswerUpdate,
    ) -> AIChatState:
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
                or question.max_selections == 1
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

    def cancel_request(self, conversation_id: str) -> AIChatState:
        for attempt in range(3):
            chat = self._get(conversation_id)
            chat.messages = [
                AIMessage(
                    id=self.repos.next_id("message"),
                    role="assistant",
                    content=self.greeting,
                ),
                AIMessage(
                    id=self.repos.next_id("message"),
                    role="assistant",
                    content=self.cancellation_message,
                ),
            ]
            chat.questions = []
            chat.draft = LessonDesignDraft(
                id=chat.draft.id,
                learner_id=chat.learner_id,
                version=chat.draft.version,
            )
            chat.can_generate = False
            chat.generation_status = None
            chat.generation_metadata = None
            try:
                return self.repos.chats.save(chat)
            except VersionConflictError:
                if attempt == 2:
                    raise
        raise VersionConflictError(
            "The lesson request could not be canceled. Please try again."
        )

    def cancel_request_dto(self, conversation_id: str) -> AIChatStateDto:
        return self.to_dto(self.cancel_request(conversation_id))

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
        draft: LessonDesignDraft | None = None,
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
                draft=draft,
            )
        return [
            by_field[field] for field in cls.core_question_fields if field in by_field
        ][:3]

    @classmethod
    def _prepare_question(
        cls,
        question: AIQuestion,
        *,
        require_fresh_confirmation: bool,
        draft: LessonDesignDraft | None = None,
    ) -> AIQuestion:
        if question.field == "selectedMaterials":
            material_options = cls._material_options_for_draft(draft)
            return question.model_copy(
                update={
                    "prompt": "Which pages should AI generate?",
                    "helper_text": (
                        "Select all or only what you need. Printing choices come later."
                    ),
                    "input_type": "multi_select",
                    "options": material_options,
                    "selected_option_ids": (
                        []
                        if require_fresh_confirmation
                        else [
                            item
                            for item in question.selected_option_ids
                            if item in {option.id for option in material_options}
                        ]
                    ),
                    "custom_answer": "",
                    "allow_custom_answer": True,
                    "required": True,
                    "max_selections": None,
                }
            )

        options: list[AIQuestionOption] = []
        selected_ids = set(question.selected_option_ids)
        for option in question.options:
            if option.source == "teacher_custom":
                continue
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
        elif custom_answer:
            options.append(
                AIQuestionOption(
                    id=f"custom-{question.id}",
                    label=custom_answer,
                    value=custom_answer,
                    description="Teacher-authored answer.",
                    icon="✎",
                    source="teacher_custom",
                )
            )

        prompt_by_field = {
            "goalText": "What should the learner practice?",
            "scenarios": "Where will the learner practice?",
        }
        helper_by_field = {
            "goalText": "Choose the AI suggestion or write a short goal.",
            "scenarios": "Pick one or two familiar situations.",
        }
        if question.field == "goalText":
            input_type = "hybrid"
            max_selections = 1
        elif question.field == "scenarios":
            input_type = "multi_select"
            max_selections = 2
        else:
            input_type = question.input_type
            max_selections = question.max_selections

        return question.model_copy(
            update={
                "prompt": prompt_by_field.get(question.field, question.prompt),
                "helper_text": helper_by_field.get(
                    question.field,
                    "Review the suggestion and confirm or edit it.",
                ),
                "input_type": input_type,
                "options": options[:4],
                "selected_option_ids": (
                    [] if require_fresh_confirmation else list(selected_ids)
                ),
                "custom_answer": custom_answer,
                "max_selections": max_selections,
            }
        )

    @classmethod
    def _material_options_for_draft(
        cls, draft: LessonDesignDraft | None
    ) -> list[AIQuestionOption]:
        if draft is None or not draft.goal_text.strip():
            return [option.model_copy(deep=True) for option in cls.printable_material_options]
        try:
            recommended = V2MaterialBlueprintService.recommended_bundle(
                LessonDesignDraftDto.model_validate(
                    draft.model_dump(mode="json", by_alias=True)
                )
            )
        except Exception:
            return [option.model_copy(deep=True) for option in cls.printable_material_options]
        icons = {
            "quantity_cards": "①",
            "matching_page": "↔",
            "visual_card": "▧",
            "help_card": "💬",
            "scenario_cards": "▤",
            "token_board": "☆",
            "data_sheet": "▦",
            "summary_template": "▤",
            "first_then_board": "→",
            "choice_board": "☑",
            "sequence_cards": "➊",
            "visual_schedule": "☷",
            "task_analysis_cards": "✓",
            "emotion_scale": "☺",
            "break_card": "⏸",
            "core_word_board": "▦",
            "social_narrative": "▤",
            "sorting_page": "◫",
        }
        option_ids = {
            "visual_card": "visual-cards",
            "quantity_cards": "quantity-cards",
            "matching_page": "matching-page",
            "scenario_cards": "scenario-cards",
            "summary_template": "summary-template",
        }
        options: list[AIQuestionOption] = []
        for material_type in recommended:
            blueprint = V2MaterialBlueprintService.blueprint(material_type)
            if blueprint is None:
                continue
            options.append(
                AIQuestionOption(
                    id=option_ids.get(
                        material_type, material_type.replace("_", "-")
                    ),
                    label=blueprint.display_name,
                    value=blueprint.display_name,
                    description=blueprint.instructional_purpose,
                    icon=icons.get(material_type, "▧"),
                    recommended=True,
                )
            )
        return options or [
            option.model_copy(deep=True) for option in cls.printable_material_options
        ]

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
