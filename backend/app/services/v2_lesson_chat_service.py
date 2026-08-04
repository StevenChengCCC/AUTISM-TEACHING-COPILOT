from __future__ import annotations

import re
from hashlib import sha256

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
    VersionConflictError,
)
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
    GoalDecisionValue,
    MaterialRequestDecisionValue,
    MaterialRequestItem,
    PackageContentPlanActionRequest,
    PracticeContextDecisionValue,
    PracticeContextItem,
    StructuredTeacherChange,
    TeacherDecision,
    utc_now,
)
from app.services.v2_learner_service import V2LearnerService
from app.services.v2_material_blueprint_service import V2MaterialBlueprintService
from app.services.v2_record_service import V2RecordService
from app.services.v2_instructional_constraint_service import (
    build_instructional_constraint_snapshot,
)
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
    cancellation_message = "That request was canceled. Tell me the corrected teaching goal when you’re ready."

    def __init__(
        self, repos: V2Repositories = repositories, ai: V2AIProvider | None = None
    ):
        self.repos = repos
        self.learners = V2LearnerService(repos)
        self.records = V2RecordService(repos)
        self.ai = ai or get_v2_ai_provider()

    def start(self, learner_id: str, *, resume_existing: bool = False) -> AIChatState:
        self.learners.get(learner_id)
        snapshot = self._snapshot(learner_id)
        conversation_id = f"conversation-{learner_id}"
        existing = self.repos.chats.get(conversation_id)
        if resume_existing and existing is not None:
            questions = self._prepare_questions(
                existing.questions,
                require_fresh_confirmation=False,
                draft=existing.draft,
            )
            draft = self._prepare_draft(existing.draft)
            self._sync_draft_from_answers(draft, questions)
            return self._with_stale_state(
                existing.model_copy(
                    update={
                        "questions": questions,
                        "draft": draft,
                        "can_generate": bool(questions)
                        and all(self._answered(item) for item in questions),
                    }
                )
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
                profile_revision=snapshot.profile_revision,
                instructional_constraint_snapshot=snapshot,
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
            snapshot = self._snapshot(initial.learner_id)
            catalog = [
                item.display_name
                for item in V2MaterialBlueprintService.CATALOG.values()
            ]
            questions, draft = self.ai.generate_lesson_questions_with_snapshot(
                learner, clean, snapshot, catalog
            )
            draft = draft.model_copy(
                update={
                    "profile_revision": snapshot.profile_revision,
                    "instructional_constraint_snapshot": snapshot,
                    "profile_stale": False,
                    "profile_stale_message": "",
                }
            )
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
            draft.supplemental_suggestions = [
                item for item in questions if item.field not in self.core_question_fields
            ]
            chat.questions = self._prepare_questions(
                questions,
                require_fresh_confirmation=True,
                draft=draft,
            )
            chat.draft = self._prepare_draft(draft)
            chat.draft.teacher_request = clean
            # The material bundle is an AI recommendation that the teacher can
            # remove from, not an empty form the teacher must build.  Apply the
            # preselected complete bundle to the draft before it is persisted.
            for question in chat.questions:
                if question.field == "selectedMaterials":
                    self._apply_answer(chat.draft, question)
                    self._record_decision(chat.draft, question, ai_default=True)
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
            change = self._parse_follow_up(clean)
            chat.draft.structured_changes.append(change)
            self._apply_structured_change(chat.draft, change)
            response = "Thanks. I’ve kept your choices and recorded that structured change."
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
            message.role == "assistant" and message.content == cls.cancellation_message
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
        for attempt in range(1 if payload.expected_draft_version is not None else 2):
            chat = self._get(conversation_id)
            if (
                payload.expected_draft_version is not None
                and chat.draft.version != payload.expected_draft_version
            ):
                raise VersionConflictError(
                    "The lesson decisions changed after this page was loaded. Refresh before saving."
                )
            chat = self._with_stale_state(chat)
            if chat.draft.profile_stale:
                raise ConflictError(chat.draft.profile_stale_message)
            chat.questions = self._prepare_questions(
                chat.questions,
                require_fresh_confirmation=False,
                draft=chat.draft,
            )
            chat.draft = self._prepare_draft(chat.draft)
            self._sync_draft_from_answers(chat.draft, chat.questions)
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
        if question.input_type == "single_select" or question.max_selections == 1:
            question.options = [
                option for option in question.options if option.source != "teacher_custom"
            ]
        question.custom_answer = payload.custom_answer.strip()
        if question.custom_answer:
            custom_id = (
                f"custom-{question.id}-{sha256(question.custom_answer.encode('utf-8')).hexdigest()[:10]}"
                if question.input_type != "single_select" and question.max_selections != 1
                else f"custom-{question.id}"
            )
            custom_option = AIQuestionOption(
                    id=custom_id,
                    label=question.custom_answer,
                    value=question.custom_answer,
                    icon="✎",
                    source="teacher_custom",
                    decision_field=self._decision_field(question.field),
                    reason="Teacher-authored value; preserve verbatim.",
                    profile_factor_ids=(
                        list(chat.draft.instructional_constraint_snapshot.profile_factor_ids)
                        if chat.draft.instructional_constraint_snapshot else []
                    ),
                    affects=self._default_affects(question.field),
                    suggestion_status=(
                        "optional" if payload.save_unsupported_for_future
                        else "blocked" if question.field == "selectedMaterials"
                        else "requires_confirmation"
                    ),
                    supported=question.field != "selectedMaterials",
                    unsupported_reason=(
                        "This custom material type is not currently supported. Change it or select a supported equivalent; it will not be remapped."
                        if question.field == "selectedMaterials" else None
                    ),
                    saved_for_future=(
                        question.field == "selectedMaterials"
                        and payload.save_unsupported_for_future
                    ),
                )
            question.options = [option for option in question.options if option.id != custom_id]
            question.options.append(custom_option)
            selected = (
                [custom_id]
                if question.input_type == "single_select"
                or question.max_selections == 1
                else list(dict.fromkeys([*selected, custom_id]))
            )
        question.selected_option_ids = selected
        self._apply_answer(chat.draft, question)
        self._record_decision(chat.draft, question)
        # Any changed core answer invalidates the derived completeness plan.
        # The concise teacher selections remain intact and can be previewed again.
        chat.draft.package_content_plan = None
        if question.field == "customNotes":
            self._apply_custom_notes(chat.draft, chat.questions)
        chat.can_generate = all(self._answered(item) for item in chat.questions) and not any(
            option.id in question.selected_option_ids and not option.supported and not option.saved_for_future
            for question in chat.questions for option in question.options
        )
        return self.repos.chats.save(chat)

    def update_answer_dto(
        self,
        conversation_id: str,
        question_id: str,
        payload: QuestionAnswerUpdate,
    ) -> AIChatStateDto:
        return self.to_dto(self.update_answer(conversation_id, question_id, payload))

    def preview_package_content_plan(
        self, conversation_id: str, expected_version: int
    ) -> AIChatStateDto:
        chat = self._get(conversation_id)
        if chat.draft.version != expected_version:
            raise VersionConflictError(
                "The lesson decisions changed after this page was loaded. Refresh before planning package contents."
            )
        if not chat.can_generate:
            raise ConflictError("Confirm the three lesson suggestions before previewing package contents")
        from app.services.v2_lesson_package_service import V2LessonPackageService

        draft = LessonDesignDraftDto.model_validate(
            chat.draft.model_dump(mode="json", by_alias=True)
        )
        plan = V2LessonPackageService(self.repos).preview_content_plan(draft)
        chat.draft.package_content_plan = plan
        return self.to_dto(self.repos.chats.save(chat))

    def adjust_package_content_plan(
        self, conversation_id: str, payload: PackageContentPlanActionRequest
    ) -> AIChatStateDto:
        chat = self._get(conversation_id)
        if chat.draft.version != payload.expected_draft_version:
            raise VersionConflictError(
                "The package preview changed after this page was loaded. Refresh before editing it."
            )
        if chat.draft.package_content_plan is None:
            raise ConflictError("Preview package contents before changing the plan")
        from app.services.v2_lesson_package_service import V2LessonPackageService
        from app.services.v2_package_content_plan_service import V2PackageContentPlanService

        plan = V2PackageContentPlanService().adjust(
            chat.draft.package_content_plan,
            action=payload.action,
            material_type=payload.material_type,
            included=payload.included,
        )
        draft = LessonDesignDraftDto.model_validate(
            chat.draft.model_dump(mode="json", by_alias=True)
        )
        chat.draft.package_content_plan = V2LessonPackageService(self.repos).validate_content_plan(draft, plan)
        return self.to_dto(self.repos.chats.save(chat))

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
        return self._with_stale_state(self._get(conversation_id))

    def refresh_recommendations(self, conversation_id: str, expected_version: int) -> AIChatState:
        chat = self._get(conversation_id)
        if chat.draft.version != expected_version:
            raise VersionConflictError(
                "The lesson decisions changed after this page was loaded. Refresh before updating recommendations."
            )
        request = chat.draft.teacher_request.strip()
        if not request:
            raise ValidationError("The original teacher request is unavailable")
        snapshot = self._snapshot(chat.learner_id)
        learner = self.learners.get(chat.learner_id)
        catalog = [item.display_name for item in V2MaterialBlueprintService.CATALOG.values()]
        generated, _ = self.ai.generate_lesson_questions_with_snapshot(
            learner, request, snapshot, catalog
        )
        refreshed = self._prepare_questions(
            generated, require_fresh_confirmation=True, draft=chat.draft
        )
        old_by_field = {item.field: item for item in chat.questions}
        merged: list[AIQuestion] = []
        for question in refreshed:
            old = old_by_field.get(question.field)
            if old is None:
                merged.append(question)
                continue
            custom = [option for option in old.options if option.source == "teacher_custom"]
            options = [*question.options, *custom]
            available = {option.id for option in options}
            merged.append(question.model_copy(update={
                "options": options,
                "selected_option_ids": [item for item in old.selected_option_ids if item in available],
                "custom_answer": old.custom_answer,
            }))
        chat.questions = merged
        chat.draft = chat.draft.model_copy(update={
            "profile_revision": snapshot.profile_revision,
            "instructional_constraint_snapshot": snapshot,
            "profile_stale": False,
            "profile_stale_message": "",
        })
        self._sync_draft_from_answers(chat.draft, chat.questions)
        chat.can_generate = all(self._answered(item) for item in chat.questions) and not any(
            option.id in question.selected_option_ids and not option.supported and not option.saved_for_future
            for question in chat.questions for option in question.options
        )
        return self.repos.chats.save(chat)

    def _get(self, conversation_id: str) -> AIChatState:
        chat = self.repos.chats.get(conversation_id)
        if not chat:
            raise NotFoundError("Lesson chat not found")
        return chat

    def _snapshot(self, learner_id: str):
        learner = self.learners.get(learner_id)
        return build_instructional_constraint_snapshot(
            learner, self.records.list_for_learner(learner_id)
        )

    def _with_stale_state(self, chat: AIChatState) -> AIChatState:
        latest = self._snapshot(chat.learner_id)
        stale = (
            bool(chat.draft.profile_revision)
            and chat.draft.profile_revision != latest.profile_revision
        )
        return chat.model_copy(
            update={
                "can_generate": False if stale else chat.can_generate,
                "draft": chat.draft.model_copy(
                    update={
                        "profile_stale": stale,
                        "profile_stale_message": (
                            "Learner information changed. Refresh suggestions to use the latest profile without losing prior decisions."
                            if stale
                            else ""
                        ),
                    }
                ),
            }
        )

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
        # Provider output is untrusted and may omit a question.  A missing
        # material question previously produced a one-page Token Board package.
        # Fill only the three product decisions, using deterministic suggestions
        # that stay editable by the teacher.
        for field in cls.core_question_fields:
            if field not in by_field:
                by_field[field] = cls._prepare_question(
                    cls._fallback_question(field, draft),
                    require_fresh_confirmation=require_fresh_confirmation,
                    draft=draft,
                )
        return [
            by_field[field] for field in cls.core_question_fields if field in by_field
        ][:3]

    @classmethod
    def _fallback_question(
        cls, field: str, draft: LessonDesignDraft | None
    ) -> AIQuestion:
        if field == "goalText":
            goal = (draft.goal_text if draft else "").strip() or (
                "Learner practices the requested skill in an observable way."
            )
            return AIQuestion(
                id="goalText",
                prompt="What should the learner practice?",
                field="goalText",
                inputType="hybrid",
                options=[],
                customAnswer=goal,
                allowCustomAnswer=True,
                maxSelections=1,
            )
        if field == "scenarios":
            labels = list(
                dict.fromkeys(
                    (draft.scenarios if draft else [])
                    or [
                        "One-to-one teaching",
                        "Small-group lesson",
                        "A familiar daily routine",
                    ]
                )
            )[:3]
            return AIQuestion(
                id="scenarios",
                prompt="Where will the learner practice?",
                field="scenarios",
                inputType="multi_select",
                options=[
                    AIQuestionOption(
                        id=f"scenario-{index + 1}",
                        label=label,
                        value=label,
                        icon="▧",
                        recommended=index < 2,
                    )
                    for index, label in enumerate(labels)
                ],
                selectedOptionIds=[
                    f"scenario-{index + 1}" for index in range(min(2, len(labels)))
                ],
                allowCustomAnswer=True,
                maxSelections=3,
            )
        return AIQuestion(
            id="selectedMaterials",
            prompt="Which pages should AI generate?",
            field="selectedMaterials",
            inputType="multi_select",
            options=cls._material_options_for_draft(draft),
            allowCustomAnswer=True,
        )

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
            known_ids = {option.id for option in material_options}
            known_material_keys = {cls._material_key(option.value) for option in material_options}
            preserved_custom = [
                (
                    option if option.source == "teacher_custom" else option.model_copy(update={
                        "supported": False,
                        "unsupported_reason": "This provider material is outside the supported catalog and will not be remapped.",
                        "suggestion_status": "blocked",
                    })
                ) for option in question.options
                if option.source == "teacher_custom" or (
                    option.id not in known_ids
                    and cls._material_key(option.value) not in known_material_keys
                )
            ]
            material_options = [*material_options, *preserved_custom]
            selected = [
                item for item in question.selected_option_ids
                if item in {option.id for option in material_options}
            ]
            return question.model_copy(
                update={
                    "prompt": "Which pages should AI generate?",
                    "helper_text": (
                        "Select all or only what you need. Printing choices come later."
                    ),
                    "input_type": "multi_select",
                    "options": material_options,
                    # Start with the complete recommended kit.  The teacher may
                    # remove any page, but never has to discover and select five
                    # separate components just to get a usable package.
                    "selected_option_ids": (
                        [option.id for option in material_options if option.source != "teacher_custom" and option.supported]
                        if require_fresh_confirmation
                        else selected
                    ),
                    "custom_answer": question.custom_answer,
                    "allow_custom_answer": True,
                    "required": True,
                    "max_selections": None,
                }
            )

        options: list[AIQuestionOption] = []
        selected_ids = set(question.selected_option_ids)
        for option in question.options:
            if option.source == "teacher_custom":
                if question.input_type != "single_select" and question.max_selections != 1:
                    options.append(option)
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
                        "decision_field": cls._decision_field(question.field),
                        "reason": option.reason or option.description,
                        "profile_factor_ids": option.profile_factor_ids or (
                            list(draft.instructional_constraint_snapshot.profile_factor_ids)
                            if draft and draft.instructional_constraint_snapshot else []
                        ),
                        "affects": option.affects or cls._default_affects(question.field),
                        "suggestion_status": (
                            "recommended" if option.recommended else "optional"
                        ),
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
                    decision_field=cls._decision_field(question.field),
                    reason="AI interpretation of the teacher request; confirmation required.",
                    affects=cls._default_affects(question.field),
                    suggestion_status="requires_confirmation",
                ),
            )
            custom_answer = ""
        elif custom_answer:
            custom_id = (
                f"custom-{question.id}-{sha256(custom_answer.encode('utf-8')).hexdigest()[:10]}"
                if question.input_type != "single_select" and question.max_selections != 1
                else f"custom-{question.id}"
            )
            if custom_id not in {item.id for item in options}:
                options.append(AIQuestionOption(
                    id=custom_id,
                    label=custom_answer,
                    value=custom_answer,
                    description="Teacher-authored answer.",
                    icon="✎",
                    source="teacher_custom",
                    decision_field=cls._decision_field(question.field),
                    reason="Teacher-authored value; preserve verbatim.",
                    affects=cls._default_affects(question.field),
                    suggestion_status="requires_confirmation",
                ))

        prompt_by_field = {
            "goalText": "What should the learner practice?",
            "scenarios": "Where will the learner practice?",
        }
        helper_by_field = {
            "goalText": "Choose the AI suggestion or write a short goal.",
            "scenarios": "Pick up to three familiar situations.",
        }
        if question.field == "goalText":
            input_type = "hybrid"
            max_selections = 1
        elif question.field == "scenarios":
            input_type = "multi_select"
            max_selections = 3
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
                "options": options[:4] if question.field == "goalText" else options[:6],
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
            return [
                option.model_copy(deep=True)
                for option in cls.printable_material_options
            ]
        try:
            recommended = V2MaterialBlueprintService.recommended_bundle(
                LessonDesignDraftDto.model_validate(
                    draft.model_dump(mode="json", by_alias=True)
                )
            )
        except Exception:
            return [
                option.model_copy(deep=True)
                for option in cls.printable_material_options
            ]
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
                    id=option_ids.get(material_type, material_type.replace("_", "-")),
                    label=blueprint.display_name,
                    value=blueprint.display_name,
                    description=blueprint.instructional_purpose,
                    icon=icons.get(material_type, "▧"),
                    recommended=True,
                    decision_field="material_requests",
                    reason=blueprint.instructional_purpose,
                    profile_factor_ids=(
                        list(draft.instructional_constraint_snapshot.profile_factor_ids)
                        if draft and draft.instructional_constraint_snapshot else []
                    ),
                    affects=[material_type],
                    suggestion_status="recommended",
                )
            )
        return options or [
            option.model_copy(deep=True) for option in cls.printable_material_options
        ]

    @staticmethod
    def _material_key(value: str) -> str:
        normalized = " ".join(value.replace("–", " ").replace("-", " ").replace("_", " ").casefold().split())
        if "summary" in normalized:
            return "summary_template"
        if "reinforcement" in normalized or "token" in normalized:
            return "token_board"
        if "visual" in normalized and "card" in normalized:
            return "visual_card"
        return normalized.replace(" ", "_")

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
            "quantity cards": "Quantity Cards",
            "matching practice": "Matching Practice",
            "matching page": "Matching Practice",
            "help card": "Help Card",
            "scenario cards": "Scenario Cards",
            "token board": "Token Board",
            "reinforcement board": "Reinforcement Board",
            "data sheet": "Data Sheet",
            "tally sheet": "Data Sheet",
            "summary template": "Summary Template",
            "first then board": "First–Then Board",
            "first–then board": "First–Then Board",
            "choice board": "Choice Board",
            "sequence cards": "Sequence Cards",
            "visual schedule": "Visual Schedule",
            "task analysis cards": "Task Analysis Cards",
            "emotion scale": "Emotion Scale",
            "break card": "Break Card",
            "core word board": "Core Word Board",
            "social narrative": "Social Narrative",
            "sorting practice": "Sorting Practice",
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

    @classmethod
    def _sync_draft_from_answers(
        cls, draft: LessonDesignDraft, questions: list[AIQuestion]
    ) -> None:
        """Keep prepared question selections and the persisted draft identical.

        A provider can return a partial material selection. The product layer
        then expands that question to the complete recommended printable kit.
        Reapplying every answered core question prevents the UI from showing five
        selected pages while the generated draft silently contains only four.
        """

        for question in questions:
            if cls._answered(question):
                cls._apply_answer(draft, question)

    @staticmethod
    def _decision_field(field: str):
        return {
            "goalText": "goal",
            "scenarios": "practice_contexts",
            "selectedMaterials": "material_requests",
        }.get(field)

    @staticmethod
    def _default_affects(field: str) -> list[str]:
        return {
            "goalText": ["lesson", "teaching_flow", "data_sheet", "materials"],
            "scenarios": ["lesson", "scenario_cards", "generalization_plan"],
            "selectedMaterials": ["materials", "printable_package"],
        }.get(field, ["lesson"])

    @classmethod
    def _record_decision(
        cls, draft: LessonDesignDraft, question: AIQuestion, *, ai_default: bool = False
    ) -> None:
        field = cls._decision_field(question.field)
        if field is None:
            return
        selected = [
            option for option in question.options
            if option.id in question.selected_option_ids
        ]
        prior = next((item for item in draft.decisions if item.field == field), None)
        has_custom = any(item.source == "teacher_custom" for item in selected)
        source = (
            "ai_recommended" if ai_default
            else "teacher_edited" if has_custom and prior is not None
            else "teacher_authored" if has_custom
            else "teacher_selected"
        )
        factor_ids = list(dict.fromkeys(
            factor_id for option in selected for factor_id in option.profile_factor_ids
        ))
        affects = list(dict.fromkeys(
            affected for option in selected for affected in (option.affects or cls._default_affects(question.field))
        ))
        reasons = [option.reason for option in selected if option.reason]
        assumptions = list(dict.fromkeys(
            assumption for option in selected for assumption in option.assumptions
        ))
        values = [option.value for option in selected]
        if field == "goal":
            text = values[0] if values else question.custom_answer
            value = GoalDecisionValue(
                teacherRequest=draft.teacher_request,
                interpretedGoal=text,
                observableBehavior=text,
                conditions=(draft.scenarios[0] if draft.scenarios else "Teacher-confirmed practice contexts"),
                successCriterion=f"Across {draft.opportunities} planned opportunities",
                acceptedResponseModes=(
                    draft.instructional_constraint_snapshot.communication.accepted_modes
                    if draft.instructional_constraint_snapshot else []
                ),
                baselineAssumptions=[draft.baseline] if draft.baseline else [],
            )
        elif field == "practice_contexts":
            value = PracticeContextDecisionValue(
                contexts=[cls._context_item(option) for option in selected]
            )
        else:
            value = MaterialRequestDecisionValue(
                materials=[
                    MaterialRequestItem(
                        requestId=option.id,
                        materialType=(option.id.replace("-", "_") if option.supported else "unsupported_custom"),
                        customLabel=option.value if option.source == "teacher_custom" else None,
                        purpose=option.description or option.reason,
                        profileFactorIds=option.profile_factor_ids,
                        supported=option.supported,
                        unsupportedReason=option.unsupported_reason,
                        required=not option.saved_for_future,
                        origin=("future_unsupported" if option.saved_for_future else "newly_generated"),
                    )
                    for option in selected
                ]
            )
        decision = TeacherDecision(
            id=prior.id if prior else f"decision-{draft.id}-{field}",
            field=field,
            source=source,
            optionIds=[option.id for option in selected],
            profileFactorIds=factor_ids,
            value=value,
            reason=" ".join(reasons),
            affects=affects or cls._default_affects(question.field),
            assumptions=assumptions,
            confirmedAt=utc_now(),
            revision=(prior.revision + 1 if prior else 1),
        )
        draft.decisions = [item for item in draft.decisions if item.field != field] + [decision]

    @staticmethod
    def _context_item(option: AIQuestionOption) -> PracticeContextItem:
        label = option.value
        match = re.split(r"\s+(?:to|→)\s+", label, maxsplit=1, flags=re.IGNORECASE)
        return PracticeContextItem(
            id=option.id,
            label=label,
            setting=label,
            transitionFrom=match[0] if len(match) == 2 else "",
            transitionTo=match[1] if len(match) == 2 else "",
            generalizationDimension="activity" if len(match) == 2 else "setting",
        )

    def _parse_follow_up(self, message: str) -> StructuredTeacherChange:
        lower = message.casefold()
        rules = [
            ("duration_change", ("minute", "duration", "longer", "shorter")),
            ("reinforcement_change", ("reinfor", "reward", "token")),
            ("prompting_change", ("prompt", "wait time", "cue")),
            ("material_change", ("material", "card", "board", "sheet", "timer")),
            ("context_change", ("context", "setting", "transition", "cleanup", "activity")),
            ("goal_clarification", ("goal", "criterion", "response", "independent")),
        ]
        change_type = next(
            (name for name, terms in rules if any(term in lower for term in terms)),
            "general_note",
        )
        return StructuredTeacherChange(
            id=self.repos.next_id("teacher-change"),
            changeType=change_type,
            originalMessage=message,
            value=message,
        )

    @staticmethod
    def _apply_structured_change(draft: LessonDesignDraft, change: StructuredTeacherChange) -> None:
        if change.change_type == "duration_change":
            draft.duration = change.value
        elif change.change_type == "reinforcement_change":
            draft.reinforcement_plan = change.value
        elif change.change_type == "prompting_change":
            draft.prompting_start = change.value
        elif change.change_type == "goal_clarification":
            draft.goal_text = change.value
            draft.observable_response = change.value
        elif change.change_type == "context_change":
            draft.scenarios = [change.value]
        elif change.change_type == "material_change":
            # Preserve the teacher text for review; unsupported material names are
            # never converted into a supported generic material here.
            draft.teacher_constraints = change.value
        else:
            draft.custom_notes = " ".join(filter(None, [draft.custom_notes, change.value]))

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
