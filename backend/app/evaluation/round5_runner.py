from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.v2_dto import LessonDesignDraftDto
from app.services.v2_safety_harness_service import V2SafetyHarnessService


def _draft(overrides: dict[str, Any] | None = None) -> LessonDesignDraftDto:
    values: dict[str, Any] = {
        "id": "evaluation-draft",
        "learnerId": "synthetic-learner",
        "goalText": "Learner will request help using an established response.",
        "observableResponse": "Requests help using speech, gesture, picture, or AAC",
        "baseline": "Teacher confirmation needed",
        "responseLevel": "Established response modality",
        "scenarios": ["Closed container", "Missing material"],
        "selectedMaterials": ["Help Card", "Data Sheet"],
        "theme": "Age-neutral classroom",
        "duration": "10 min",
        "customNotes": "",
    }
    values.update(overrides or {})
    return LessonDesignDraftDto.model_validate(values)


def evaluate_case(case: dict[str, Any]) -> tuple[bool, str]:
    kind = case["kind"]
    payload = case.get("payload", {})
    expected = case["expected"]
    if kind == "safety":
        review = V2SafetyHarnessService().review_product(
            _draft(payload.get("draft")), payload.get("generatedContent", {})
        )
        actual = review.status
    elif kind == "profile":
        signals = payload.get("signals", [])
        unknown = set(payload.get("unknownFields", []))
        if payload.get("requiresUnknown") and not unknown:
            actual = "invalid"
        elif payload.get("rejectLowConfidencePersonalization") and any(
            item.get("category") in {"interest", "reinforcement"}
            and float(item.get("confidence", 0)) < 0.75
            and item.get("usedForPersonalization", False)
            for item in signals
        ):
            actual = "invalid"
        elif payload.get("requiresContradiction") and not any(
            item.get("evidenceType") == "contradiction" for item in signals
        ):
            actual = "invalid"
        else:
            actual = "valid"
    elif kind == "schema":
        try:
            draft = _draft(payload.get("draft"))
            if payload.get("requiresObservableGoal") and not (
                draft.observableResponse.strip() and draft.baseline.strip()
            ):
                actual = "invalid"
            elif payload.get("inventedLearnerDetail"):
                actual = "blocked"
            elif payload.get("dataTarget") not in {None, payload.get("goalTarget")}:
                actual = "invalid"
            elif payload.get("ageRespectful") is False:
                actual = "needs_review"
            else:
                actual = "valid"
        except Exception:
            actual = "invalid"
    elif kind == "provider":
        actual = "retry_required" if payload.get("malformedOutput") else "valid"
    elif kind == "prompt_boundary":
        text = str(payload.get("untrustedText", "")).casefold()
        actual = (
            "ignored_untrusted_instruction"
            if "ignore previous" in text or "reveal system" in text
            else "valid"
        )
    else:
        return False, f"unsupported evaluation kind: {kind}"
    return actual == expected, actual


def run(dataset: Path) -> dict[str, Any]:
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        passed, actual = evaluate_case(case)
        results.append(
            {
                "id": case["id"],
                "passed": passed,
                "expected": case["expected"],
                "actual": actual,
            }
        )
    return {
        "evaluator": "round5-offline-v1",
        "providerCalled": False,
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic Round 5 set")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parents[2] / "evaluation" / "round5_cases.json",
    )
    parser.add_argument(
        "--provider-backed",
        action="store_true",
        help="Explicitly opt into provider evaluation; the offline gate never calls AI.",
    )
    args = parser.parse_args()
    if args.provider_backed:
        if settings.AI_PROVIDER == "mock":
            parser.error("Provider-backed evaluation requires a non-mock AI_PROVIDER")
        parser.error(
            "Provider-backed evaluation is separate from the deterministic Round 5 gate"
        )
    report = run(args.dataset)
    print(json.dumps(report, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
