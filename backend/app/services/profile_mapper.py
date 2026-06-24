import json
from app.models.entities import ChildProfile


def child_to_dict(child: ChildProfile) -> dict:
    return {
        "id": child.id,
        "code": child.code,
        "age": child.age,
        "diagnosis_level": child.diagnosis_level,
        "attention_span_minutes": child.attention_span_minutes,
        "communication_level": child.communication_level,
        "interests": json.loads(child.interests_json or "[]"),
        "reinforcers": json.loads(child.reinforcers_json or "[]"),
        "behavior_notes": child.behavior_notes or "",
        "notes": child.notes or "",
    }
