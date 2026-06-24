from app.domain.models import ChildProfile
from app.schemas.dto import ProfileCompletenessResult, ProfileQuestion

REQUIRED_PROFILE_FIELDS = [
    "attention_span_minutes",
    "communication_mode",
    "current_level",
    "preferred_reinforcers",
    "prompting_that_works",
    "avoid_notes",
]

GUIDED_QUESTIONS = {
    "attention_span_minutes": "About how many minutes can the learner stay with a structured 1:1 task before needing reinforcement or a break?",
    "communication_mode": "How does the learner currently communicate during teaching: speech, AAC, PECS, gestures, pointing, or another mode?",
    "current_level": "What can the learner do independently right now for this domain or prerequisite skill?",
    "preferred_reinforcers": "Which reinforcers reliably work right now, and which ones lose value quickly?",
    "prompting_that_works": "Which prompts help without causing frustration: gesture, model, visual, verbal, physical, or another prompt?",
    "avoid_notes": "What should the teacher avoid during sessions, such as triggers, disliked materials, wording, or sensory issues?",
}

FIELD_REASONS = {
    "attention_span_minutes": "Needed for deterministic attention-aware session segmentation.",
    "communication_mode": "Needed so scripts and response expectations match how the learner communicates.",
    "current_level": "Needed to keep the teaching goal at an appropriate starting point.",
    "preferred_reinforcers": "Needed for reinforcement rotation and saturation warnings.",
    "prompting_that_works": "Needed to plan prompt hierarchy without guessing.",
    "avoid_notes": "Needed to reduce avoidable distress and unsafe session design.",
}


class ProfileCompletenessService:
    def check(self, child: ChildProfile) -> ProfileCompletenessResult:
        profile_values = {
            "attention_span_minutes": child.attention_span_minutes,
            "communication_mode": child.communication_mode or child.communication_level,
            "current_level": child.current_level,
            "preferred_reinforcers": child.preferred_reinforcers_json
            or child.reinforcers_json,
            "prompting_that_works": child.prompting_that_works,
            "avoid_notes": child.avoid_notes,
        }
        missing = [
            field
            for field in REQUIRED_PROFILE_FIELDS
            if self._is_missing(profile_values[field])
        ]
        return ProfileCompletenessResult(
            child_id=child.id,
            is_complete=not missing,
            missing_fields=missing,
            guided_questions=[
                ProfileQuestion(
                    field=field,
                    question=GUIDED_QUESTIONS[field],
                    reason=FIELD_REASONS[field],
                )
                for field in missing
            ],
        )

    def _is_missing(self, value) -> bool:
        if value is None:
            return True
        if isinstance(value, int):
            return value <= 0
        if isinstance(value, str):
            stripped = value.strip()
            return not stripped or stripped == "[]"
        return not bool(value)
