import json
from app.models.entities import ChildProfile


def child_to_dict(child: ChildProfile) -> dict:
    return {
        "id": child.id,
        "code": child.code,
        "age": child.age,
        "diagnosis_level": child.diagnosis_level,
        "attention_span_minutes": child.attention_span_minutes,
        "communication_mode": child.communication_mode or child.communication_level,
        "communication_level": child.communication_level,
        "current_level": child.current_level or "",
        "interests": json.loads(child.interests_json or "[]"),
        "reinforcers": json.loads(child.reinforcers_json or "[]"),
        "preferred_reinforcers": json.loads(
            child.preferred_reinforcers_json or child.reinforcers_json or "[]"
        ),
        "prompting_that_works": child.prompting_that_works or "",
        "avoid_notes": child.avoid_notes or "",
        "behavior_notes": child.behavior_notes or "",
        "notes": child.notes or "",
    }
