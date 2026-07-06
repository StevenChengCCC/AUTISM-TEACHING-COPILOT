from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from itertools import count
from threading import RLock
from typing import Generic, TypeVar

from app.schemas.v2_dto import (
    AIChatState,
    GeneratedMaterial,
    LearnerProfile,
    LearnerRecord,
    LessonPackage,
    LessonSession,
    MaterialLibraryItem,
    LearnerProgressSummaryDto,
    ProgressDataPointDto,
    ProgressObservation,
    ProgressSignalDto,
    RecentLessonDto,
)

T = TypeVar("T")


class InMemoryV2Repository(Generic[T]):
    """Thread-safe database-shaped repository used by Backend v2.

    Services depend only on list/get/save behavior so this adapter can later be
    replaced by SQLAlchemy repositories without changing business logic.
    Returned values are copies to prevent callers from mutating stored state.
    """

    def __init__(self, seed: list[T] | None = None, key_field: str = "id"):
        self._lock = RLock()
        self._items: dict[str, T] = {}
        self._key_field = key_field
        for item in seed or []:
            self._items[getattr(item, self._key_field)] = deepcopy(item)

    def list(self) -> list[T]:
        with self._lock:
            return deepcopy(list(self._items.values()))

    def get(self, item_id: str) -> T | None:
        with self._lock:
            item = self._items.get(item_id)
            return deepcopy(item) if item is not None else None

    def save(self, item: T) -> T:
        with self._lock:
            self._items[getattr(item, self._key_field)] = deepcopy(item)
            return deepcopy(item)

    def create(self, item: T) -> T:
        return self.save(item)

    def update(self, item: T) -> T:
        return self.save(item)


# Backward-compatible name for existing v2 services.
InMemoryRepository = InMemoryV2Repository


class RecordRepository(InMemoryV2Repository[LearnerRecord]):
    def for_learner(self, learner_id: str) -> list[LearnerRecord]:
        return [item for item in self.list() if item.learner_id == learner_id]


class MaterialRepository(InMemoryV2Repository[GeneratedMaterial]):
    def for_package(self, package_id: str) -> list[GeneratedMaterial]:
        return [
            item
            for item in self.list()
            if getattr(item, "package_id", getattr(item, "packageId", None))
            == package_id
        ]


class ProgressRepository:
    def __init__(self):
        self._lock = RLock()
        self._items: list[ProgressObservation] = []

    def add(self, item: ProgressObservation) -> ProgressObservation:
        with self._lock:
            self._items.append(deepcopy(item))
            return deepcopy(item)

    def for_learner(self, learner_id: str) -> list[ProgressObservation]:
        with self._lock:
            return deepcopy([item for item in self._items if item.learner_id == learner_id])


def _now() -> datetime:
    """Stable seed timestamp; runtime services use utc_now for new records."""

    return datetime(2025, 5, 12, 10, 21, tzinfo=timezone.utc)


class V2Repositories:
    """Application repository registry; production wiring can inject persistent adapters."""

    def __init__(self):
        learners = [
            LearnerProfile(id="a102", code="Learner A-102", age=7, avatar="👦🏻", tags=["Visual support", "Short attention span", "Vehicles"], interests=["Vehicles", "Puzzles"], support_needs=["Visual support", "Short attention span"], reinforcement_preferences=["Praise", "Token board"], communication_mode="Short phrases", attention_profile="Benefits from short, structured activities.", notes="Benefits from visual prompts and concise instructions."),
            LearnerProfile(id="b214", code="Learner B-214", age=9, avatar="👧🏻", tags=["AAC", "Communication"], interests=["Music", "Animals"], support_needs=["AAC", "Processing time"], reinforcement_preferences=["Music break", "Praise"], communication_mode="AAC device and gestures", attention_profile="Benefits from predictable pacing and wait time.", notes="Benefits from clear choices and wait time."),
            LearnerProfile(id="c087", code="Learner C-087", age=6, avatar="👦🏽", tags=["Visual support", "Attention"], interests=["Building blocks"], support_needs=["Visual support", "Choice making"], reinforcement_preferences=["Movement break", "Tokens"], communication_mode="Single words and picture exchange", attention_profile="Benefits from movement between short activities.", notes="Needs movement breaks and visual transitions."),
            LearnerProfile(id="n501", code="Learner N-501", age=7, avatar="🧒🏻", tags=["Visual prompts", "Short phrases"], interests=["Cars", "Puzzles"], support_needs=["Visual prompts", "Short attention span"], reinforcement_preferences=["Praise", "Tokens"], communication_mode="Short phrases", attention_profile="Hands-on, visual, structured activities.", notes="New learner profile ready for teacher review."),
        ]
        records = [
            LearnerRecord(id="record-1", learner_id="a102", file_name="IEP summary.pdf", file_type="PDF", status="reviewed", uploaded_at=_now(), extracted_text="Uses short phrases and benefits from visual schedules."),
            LearnerRecord(id="record-2", learner_id="n501", file_name="IEP summary.pdf", file_type="PDF", status="ready", uploaded_at=_now(), extracted_text="Uses short phrases with visual prompts."),
            LearnerRecord(id="record-3", learner_id="n501", file_name="Intake notes.docx", file_type="DOCX", status="reviewed", uploaded_at=_now(), extracted_text="Enjoys cars, puzzles, and hands-on routines."),
            LearnerRecord(id="record-4", learner_id="n501", file_name="Session notes May 12.txt", file_type="TXT", status="reviewed", uploaded_at=_now(), extracted_text="Keep activities short and provide multiple examples."),
        ]
        sessions = [
            LessonSession(id="session-1", learner_id="a102", goal="Asking for Help", status="planned"),
            LessonSession(id="session-2", learner_id="b214", goal="Following Directions", status="completed"),
            LessonSession(id="session-3", learner_id="n501", goal="Identify Emotions", status="draft"),
            LessonSession(id="session-4", learner_id="c087", goal="Sorting Objects", status="in_progress"),
        ]
        library = [
            MaterialLibraryItem(id="library-1", title="First-Then Card", type="Visual Cards", thumbnail_label="First → Then", source="template", created_at=_now()),
            MaterialLibraryItem(id="library-2", title="Emotion Card", type="Visual Cards", thumbnail_label="How do I feel?", source="template", created_at=_now()),
            MaterialLibraryItem(id="library-3", title="Token Board", type="Token Boards", thumbnail_label="I am working for ⭐", source="template", created_at=_now()),
            MaterialLibraryItem(id="library-4", title="Data Sheet", type="Data Sheets", thumbnail_label="Data Collection", source="template", created_at=_now()),
            MaterialLibraryItem(id="library-5", title="Choice Board", type="Visual Cards", thumbnail_label="My Choices", source="template", created_at=_now()),
            MaterialLibraryItem(id="library-6", title="Help Card", type="Help Cards", thumbnail_label="Asking for Help", source="template", created_at=_now()),
            MaterialLibraryItem(id="library-7", title="Summary Template", type="Summary Templates", thumbnail_label="Session Summary", source="template", created_at=_now()),
        ]
        recent_lessons = [
            RecentLessonDto(id="recent-1", learnerId="a102", title="Asking for Help", date="2025-05-12"),
            RecentLessonDto(id="recent-2", learnerId="a102", title="Choosing with Pictures", date="2025-05-08"),
            RecentLessonDto(id="recent-3", learnerId="b214", title="Following Directions", date="2025-05-11"),
        ]
        progress_summaries = [
            LearnerProgressSummaryDto(
                learnerId="a102",
                currentGoal="Asking for Help",
                accuracyPercent=58,
                independencePercent=42,
                sessionsPracticed=4,
                currentPromptLevel="Level 2",
                trend="Slow, uneven growth with emerging independence",
                message="Plateau does not mean no progress.",
            )
        ]
        progress_signals = [
            ProgressSignalDto(id="signal-engagement", type="engagement", label="Engagement", description="Participates longer when vehicle visuals are used.", status="improving"),
            ProgressSignalDto(id="signal-prompts", type="prompt_fading", label="Prompt Fading", description="Moving inconsistently from Level 3 toward Level 2 prompts.", status="emerging"),
            ProgressSignalDto(id="signal-generalization", type="generalization", label="Generalization Attempts", description="Tried asking for help in one new classroom routine.", status="emerging"),
            ProgressSignalDto(id="signal-regulation", type="regulation_recovery", label="Regulation / Recovery", description="Returns to the activity after a short visual break.", status="stable"),
            ProgressSignalDto(id="signal-participation", type="participation", label="Participation", description="Joins most practice opportunities with support.", status="stable"),
            ProgressSignalDto(id="signal-independence", type="independence", label="Independence", description="A few responses now occur before the full prompt.", status="improving"),
        ]
        progress_data = [
            ProgressDataPointDto(id="progress-1", learnerId="a102", sessionDate="2025-04-21", goal="Asking for Help", opportunities=8, accuracyPercent=50, independencePercent=25, promptLevel="Level 3", signalsHighlighted=["engagement", "participation"], teacherNotes="Participated with visual support. One independent attempt was a meaningful small win."),
            ProgressDataPointDto(id="progress-2", learnerId="a102", sessionDate="2025-04-28", goal="Asking for Help", opportunities=7, accuracyPercent=57, independencePercent=29, promptLevel="Level 3", signalsHighlighted=["regulation_recovery", "participation"], teacherNotes="Accuracy varied after a transition, but recovery was quicker with a visual break."),
            ProgressDataPointDto(id="progress-3", learnerId="a102", sessionDate="2025-05-05", goal="Asking for Help", opportunities=9, accuracyPercent=56, independencePercent=33, promptLevel="Level 2", signalsHighlighted=["prompt_fading", "engagement"], teacherNotes="Accepted a lighter prompt in several trials; progress remains uneven and is not mastery."),
            ProgressDataPointDto(id="progress-4", learnerId="a102", sessionDate="2025-05-12", goal="Asking for Help", opportunities=8, accuracyPercent=58, independencePercent=42, promptLevel="Level 2", signalsHighlighted=["independence", "generalization"], teacherNotes="Asked for help once in a new routine. Celebrate the attempt and continue gradual support."),
        ]
        progress_observations = [
            ProgressObservation(session_id="session-1", learner_id="a102", independence_level=1, prompt_level=3, engagement_level=2, regulation_level=2, generalization_contexts=[], notes="Participated with visual support; early small win.", observed_at=datetime(2025, 4, 21, tzinfo=timezone.utc)),
            ProgressObservation(session_id="session-1", learner_id="a102", independence_level=1, prompt_level=3, engagement_level=3, regulation_level=2, generalization_contexts=[], notes="Recovery improved after a brief visual break.", observed_at=datetime(2025, 4, 28, tzinfo=timezone.utc)),
            ProgressObservation(session_id="session-1", learner_id="a102", independence_level=2, prompt_level=2, engagement_level=3, regulation_level=2, generalization_contexts=["table work"], notes="Accepted lighter prompts; skill is still emerging.", observed_at=datetime(2025, 5, 5, tzinfo=timezone.utc)),
            ProgressObservation(session_id="session-1", learner_id="a102", independence_level=2, prompt_level=2, engagement_level=3, regulation_level=3, generalization_contexts=["table work", "classroom routine"], notes="One spontaneous attempt in a new routine; not yet mastery.", observed_at=_now()),
        ]
        self.learners = InMemoryV2Repository[LearnerProfile](learners)
        self.records = RecordRepository(records)
        self.conversations = InMemoryV2Repository[AIChatState](key_field="conversation_id")
        self.chats = self.conversations
        self.lesson_packages = InMemoryV2Repository[LessonPackage]()
        self.packages = self.lesson_packages
        self.materials = MaterialRepository()
        self.generated_materials = self.materials
        self.materials_library = InMemoryV2Repository[MaterialLibraryItem](library)
        self.library = self.materials_library
        self.sessions = InMemoryV2Repository[LessonSession](sessions)
        self.recent_lessons = InMemoryV2Repository[RecentLessonDto](recent_lessons)
        self.progress_summaries = InMemoryV2Repository[LearnerProgressSummaryDto](progress_summaries, key_field="learnerId")
        self.progress_signals = InMemoryV2Repository[ProgressSignalDto](progress_signals)
        self.progress_data = InMemoryV2Repository[ProgressDataPointDto](progress_data)
        self.progress = ProgressRepository()
        for observation in progress_observations:
            self.progress.add(observation)
        self.ids = count(1000)

    def next_id(self, prefix: str) -> str:
        with self.learners._lock:
            return f"{prefix}-{next(self.ids)}"


repositories = V2Repositories()
