#!/usr/bin/env python3
"""Run a bounded paid staging round for multi-exemplar object teaching.

The fixture is fully synthetic. The command captures paid provider output and
stops before teacher approval so every image can be reviewed by a human.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_paid_staging_quality_round import (
    ApiClient,
    PLACEHOLDER_PATTERNS,
    RoundFailure,
    _contains_unsafe_directive,
    _flatten_strings,
    _profile_factor,
    _renderable_package_text,
    _safe_package_snapshot,
    _save_assets,
    _save_deterministic_fallbacks,
)


TERMINAL_JOBS = {"completed", "partially_complete", "failed"}
SELECTED_TYPES = {"visual_card", "data_sheet", "summary_template"}


def _normalized_profile() -> dict[str, Any]:
    factors = [
        _profile_factor(
            "communication-point-or-name",
            "communication",
            "Pointing to the named object or saying its name are both accepted.",
            constraints=["accept_response_mode=pointing", "accept_response_mode=speech"],
        ),
        _profile_factor(
            "wait-five-seconds",
            "prompting",
            "Wait at least five seconds before prompting.",
            constraints=["minimum_processing_wait_seconds=5"],
        ),
        _profile_factor(
            "least-to-most",
            "prompting",
            "Independent opportunity, gesture to the choices, then a brief verbal cue.",
        ),
        _profile_factor(
            "no-hand-over-hand",
            "prohibited_item",
            "Hand-over-hand prompting is prohibited.",
        ),
        _profile_factor(
            "low-clutter",
            "visual_access",
            "Use high-contrast, low-clutter cards with one isolated real object per image.",
        ),
        _profile_factor(
            "pointing-access",
            "motor_access",
            "Allow pointing or eye-gaze selection; do not require handwriting or cutting.",
        ),
        _profile_factor(
            "fruit-interest",
            "current_interest",
            "The learner enjoys sorting produce during pretend grocery activities.",
        ),
        _profile_factor(
            "neutral-feedback",
            "error_correction",
            "Use neutral feedback, reduce the field, model once, and offer a new opportunity.",
        ),
        _profile_factor(
            "no-food-reward",
            "reinforcement",
            "Food rewards are not approved; use specific verbal acknowledgment only.",
            status="not_approved",
        ),
    ]
    return {
        "learnerId": "synthetic-pending",
        "age": 9,
        "factors": factors,
        "confirmedFactorIds": [
            item["id"] for item in factors if item["status"] == "confirmed_current"
        ],
        "unconfirmedFactorIds": [],
        "historicalFactorIds": [],
        "excludedFactorIds": [
            item["id"]
            for item in factors
            if item["status"] == "not_approved"
            or item["category"] == "prohibited_item"
        ],
        "blockingIssues": [],
        "summary": {
            "communication": "Pointing or speech",
            "supports": ["five-second wait", "low-clutter object cards"],
            "currentInterests": ["pretend grocery sorting"],
            "learningFormat": "Brief tabletop concept lessons",
            "keyTeachingNotes": ["Vary examples", "No physical prompting"],
        },
    }


def _synthetic_profile(suffix: str) -> dict[str, Any]:
    return {
        "code": f"SYN-APPLE-{suffix}",
        "age": 9,
        "tags": ["Synthetic acceptance case", "Concept generalization"],
        "interests": ["pretend grocery sorting", "fruit baskets"],
        "supportNeeds": [
            "five seconds of processing time before prompting",
            "one isolated object per image",
            "multiple visibly different examples of the same concept",
        ],
        "reinforcementPreferences": ["specific verbal acknowledgment"],
        "communicationMode": "Pointing to the correct card or saying Apple are both valid",
        "attentionProfile": "Works best with six large low-clutter cards in a short lesson",
        "notes": "Fully synthetic paid-provider acceptance profile. No real learner data.",
        "strengths": ["matches identical pictures", "sorts familiar grocery objects"],
        "sensoryPreferences": ["quiet instruction", "plain backgrounds"],
        "knownChallenges": [
            "may memorize one picture instead of recognizing varied examples",
            "needs practice across different colors, shapes, and views",
        ],
        "promptingPreferences": [
            "wait five seconds",
            "gesture to the choices, then use one brief verbal cue",
            "never use hand-over-hand prompting",
        ],
        "currentGoals": ["identify or name an apple across varied real examples"],
        "readingLevel": "single familiar object words",
        "activityDurationPreference": "6-8 minute tabletop lesson",
        "responseOptions": ["pointing", "eye-gaze selection", "saying Apple"],
        "receptiveSupports": ["one-step directions", "field of two or three"],
        "expressiveSupports": ["speech accepted", "pointing accepted"],
        "environmentalConsiderations": ["tabletop object identification"],
        "effectiveSupports": ["varied real-object photographs", "neutral correction"],
        "ineffectiveSupports": ["repeating one identical picture", "busy scene images"],
        "independenceProfile": (
            "Independent means pointing to or naming Apple after the natural direction "
            "and five-second wait, without a teacher prompt."
        ),
        "emergingSkills": ["recognizing the same object across changes in appearance"],
        "generalizationProfile": "Begin with varied visual exemplars before changing settings",
        "breakPreferences": ["brief pause available on request"],
        "classroomBarriers": ["busy backgrounds", "visually similar distractors too early"],
        "normalizedProfile": _normalized_profile(),
        "profileReviewStatus": "draft",
    }


def _teacher_request() -> str:
    return (
        "Create a short, age-respectful concept lesson that teaches the learner to identify "
        "or name an apple across varied real examples. The essential learner material is a "
        "printable set of six Apple object-exemplar cards: visibly different red, green, and "
        "yellow apples, different angles, a whole apple, a cut half showing the inside, and "
        "clear slices. Every image must show only the apple exemplar on a plain background—"
        "no teacher, child, hand, classroom scene, other fruit, embedded text, or decorative "
        "props. Accept pointing or saying Apple, wait five seconds, and never use hand-over-"
        "hand prompting. Select Visual Cards, Data Sheet, and Summary Template. Do not add "
        "Scenario Cards; the varied object exemplars are the instructional practice set."
    )


def _answer(question: dict[str, Any]) -> tuple[list[str], str]:
    field = question.get("field")
    options = [item for item in question.get("options", []) if item.get("supported", True)]
    if field == "goalText":
        return [], "Identify or name Apple across six visibly varied real-object exemplars."
    if field == "scenarios":
        return [], "Tabletop object identification with a field of two or three cards."
    if field == "selectedMaterials":
        wanted = ("visual card", "data sheet", "summary template", "lesson summary")
        selected = []
        for item in options:
            text = " ".join(str(item.get(key, "")) for key in ("label", "value")).casefold()
            if any(value in text for value in wanted):
                selected.append(item["id"])
        selected = list(dict.fromkeys(selected))
        if len(selected) != 3:
            raise RoundFailure("The supported material catalog did not expose all three requested pages")
        return selected, ""
    recommended = [item["id"] for item in options if item.get("recommended")]
    if recommended:
        return recommended[:1], ""
    if options and question.get("required"):
        return [options[0]["id"]], ""
    return [], ""


def _package_text(package: dict[str, Any]) -> str:
    return _renderable_package_text(package)


def _quality(
    chat: dict[str, Any],
    package: dict[str, Any],
    job: dict[str, Any],
    assets: list[dict[str, Any]],
) -> dict[str, Any]:
    materials = package.get("materials", [])
    types = {item.get("type") for item in materials}
    visual = next((item for item in materials if item.get("type") == "visual_card"), {})
    items = [
        item
        for item in (visual.get("content") or {}).get("visualItems", [])
        if (item.get("assetRole") or item.get("role")) == "concept_exemplar"
    ]
    asset_by_id = {item["assetId"]: item for item in assets}
    exemplar_assets = [asset_by_id.get(item.get("imageAssetId")) for item in items]
    exemplar_assets = [item for item in exemplar_assets if item]
    text = _package_text(package)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, evidence: str) -> None:
        checks.append({"id": check_id, "passed": bool(passed), "evidence": evidence})

    metadata = chat.get("generationMetadata") or {}
    check(
        "paid_text_provider",
        metadata.get("outputSource") == "provider",
        f"provider={metadata.get('provider') or 'unknown'}; model={metadata.get('model') or 'unknown'}",
    )
    check("selected_materials_preserved", SELECTED_TYPES <= types, ", ".join(sorted(types)))
    check("scenario_cards_excluded", "scenario_cards" not in types, ", ".join(sorted(types)))
    check("six_concept_exemplars", len(items) == 6, f"planned={len(items)}")
    check(
        "consistent_child_label",
        len(items) == 6 and {str(item.get("label")) for item in items} == {"Apple"},
        str([item.get("label") for item in items]),
    )
    concepts = [str(item.get("concept") or "") for item in items]
    check("distinct_semantic_variations", len(set(concepts)) == 6, f"unique={len(set(concepts))}/6")
    concept_text = " ".join(concepts).casefold()
    check(
        "variation_coverage",
        all(term in concept_text for term in ("red", "green", "yellow", "half", "slices", "above")),
        "red/green/yellow/half/slices/above semantic plan",
    )
    check("six_paid_exemplar_images", len(exemplar_assets) == 6, f"saved={len(exemplar_assets)}")
    hashes = [item["sha256"] for item in exemplar_assets]
    check("exemplar_images_not_duplicated", len(hashes) == len(set(hashes)) == 6, f"unique={len(set(hashes))}/6")
    check(
        "exemplars_await_human_review",
        len(exemplar_assets) == 6 and all(not item.get("approved") for item in exemplar_assets),
        "no automatic approval",
    )
    check(
        "semantic_and_safety_validation",
        all(
            ((item.get("materialSpec") or {}).get("semanticValidation") or {}).get("status") == "passed"
            and ((item.get("materialSpec") or {}).get("safetyValidation") or {}).get("status") == "passed"
            for item in materials
        ),
        "all current material revisions",
    )
    check("generation_job_completed", job.get("status") == "completed", f"status={job.get('status')}")
    check(
        "no_placeholders",
        not any(re.search(pattern, text, re.I) for pattern in PLACEHOLDER_PATTERNS),
        "placeholder scan",
    )
    check("no_prohibited_directive", not _contains_unsafe_directive(text), "directive scan")
    return {
        "overallStatus": "PASS" if all(item["passed"] for item in checks) else "NEEDS_REVIEW",
        "checks": checks,
        "materialCount": len(materials),
        "materialTypes": sorted(str(item) for item in types if item),
        "savedVisualCount": len(assets),
        "paidExemplarCount": len(exemplar_assets),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paid concept-exemplar staging round",
        "",
        f"- Status: **{report['quality']['overallStatus']}**",
        f"- Materials: {report['quality']['materialCount']}",
        f"- Paid Apple exemplars: {report['quality']['paidExemplarCount']}",
        "- Synthetic data only: yes",
        "- Teacher/visual approval performed: no",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for item in report["quality"]["checks"]:
        lines.append(
            f"| {item['id']} | {'PASS' if item['passed'] else 'FAIL'} | "
            f"{str(item['evidence']).replace('|', '\\|')} |"
        )
    lines.extend(
        [
            "",
            "## Required human gate",
            "",
            "Inspect all six Apple images for correct object identity, meaningful variation, plain backgrounds, no distractors, no embedded text, age respectfulness, and printable clarity before approval.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_paid_ai:
        raise RoundFailure("Refusing to run without --confirm-paid-ai")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RoundFailure("Token file is empty")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    client = ApiClient(args.api_base, token, timeout=args.request_timeout)
    suffix = datetime.now(timezone.utc).strftime("%m%d%H%M%S")

    if args.resume_conversation_id:
        chat = client.request("GET", f"/api/v2/lesson-chat/{args.resume_conversation_id}")
        learner = {"id": chat["learnerId"]}
    else:
        learner = client.request("POST", "/api/v2/learners", _synthetic_profile(suffix))
        if learner.get("profileReviewStatus") != "confirmed":
            learner = client.request(
                "POST",
                f"/api/v2/learners/{learner['id']}/profile/confirm",
                {"expectedVersion": learner["version"]},
            )
        chat = client.request(
            "POST", "/api/v2/lesson-chat/start", {"learnerId": learner["id"], "resumeExisting": False}
        )
        chat = client.request(
            "POST",
            "/api/v2/lesson-chat/message",
            {"conversationId": chat["conversationId"], "learnerId": learner["id"], "message": _teacher_request()},
        )
    if (chat.get("generationMetadata") or {}).get("outputSource") != "provider":
        raise RoundFailure("Lesson interpretation did not come from the configured paid provider")
    for question in list(chat.get("questions", [])):
        selected, custom = _answer(question)
        chat = client.request(
            "PATCH",
            f"/api/v2/lesson-chat/{chat['conversationId']}/answers",
            {
                "questionId": question["id"],
                "selectedOptionIds": selected,
                "customAnswer": custom,
                "expectedDraftVersion": chat["draft"]["version"],
                "saveUnsupportedForFuture": False,
            },
        )
    chat = client.request(
        "POST",
        f"/api/v2/lesson-chat/{chat['conversationId']}/content-plan",
        {"expectedDraftVersion": chat["draft"]["version"]},
    )
    plan = chat["draft"].get("packageContentPlan") or {}
    included = {
        *[item.get("materialType") for item in plan.get("teacherSelectedCore", [])],
        *[
            item.get("materialType")
            for item in plan.get("requiredCompanions", [])
            if item.get("included")
        ],
        *[
            item.get("materialType")
            for item in plan.get("optionalEnrichments", [])
            if item.get("defaultIncluded")
        ],
    }
    if "scenario_cards" in included:
        raise RoundFailure("Concept package incorrectly requires Scenario Cards before generation")
    if not chat.get("canGenerate"):
        raise RoundFailure("Teacher-confirmed concept draft is not generation-ready")

    package = client.request("POST", "/api/v2/lesson-packages/generate", chat["draft"])
    job = client.request("GET", f"/api/v2/lesson-packages/{package['id']}/generation-job")
    estimated = int((job.get("cost") or {}).get("estimatedVisualCount") or 0)
    if estimated > args.max_visuals:
        raise RoundFailure(f"Server estimated {estimated} visuals, exceeding --max-visuals")
    deadline = time.monotonic() + args.max_wait_seconds
    while job.get("status") not in TERMINAL_JOBS:
        if time.monotonic() >= deadline:
            raise RoundFailure("Generation job exceeded the bounded wait time")
        time.sleep(args.poll_seconds)
        job = client.request("GET", f"/api/v2/generation-jobs/{job['jobId']}")

    package = client.request("GET", f"/api/v2/lesson-packages/{package['id']}")
    assets = _save_assets(client, package.get("materials", []), args.output_dir)
    fallbacks = _save_deterministic_fallbacks(package.get("materials", []), args.output_dir)
    quality = _quality(chat, package, job, assets)
    report = {
        "schemaVersion": 1,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "environment": "staging",
        "synthetic": True,
        "paidAiConfirmed": True,
        "learnerId": learner["id"],
        "conversationId": chat["conversationId"],
        "draftId": chat["draft"]["id"],
        "packageId": package["id"],
        "jobId": job["jobId"],
        "job": {
            "status": job.get("status"),
            "provider": job.get("provider"),
            "model": job.get("model"),
            "attempts": job.get("attempts"),
            "cost": job.get("cost"),
            "stages": job.get("stages", []),
        },
        "assets": assets,
        "fallbacks": fallbacks,
        "quality": quality,
        "package": _safe_package_snapshot(package),
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="https://api.autismteachingcopilot.com")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-visuals", type=int, default=10)
    parser.add_argument("--max-wait-seconds", type=int, default=1200)
    parser.add_argument("--request-timeout", type=int, default=90)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument(
        "--resume-conversation-id",
        help="Reuse a persisted synthetic paid interpretation instead of paying to interpret it again.",
    )
    parser.add_argument("--confirm-paid-ai", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, RoundFailure, ValueError) as exc:
        if args.output_dir.is_dir() and not (args.output_dir / "report.json").exists():
            (args.output_dir / "failure.md").write_text(
                "# Paid concept-exemplar round failed\n\n"
                f"- Captured at: {datetime.now(timezone.utc).isoformat()}\n"
                "- Synthetic data only: yes\n"
                "- Automatic teacher or visual approval: no\n"
                f"- Failure: {exc}\n",
                encoding="utf-8",
            )
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        f"{report['quality']['overallStatus']}: "
        f"{report['quality']['materialCount']} materials, "
        f"{report['quality']['paidExemplarCount']} paid Apple exemplars"
    )
    print(f"Saved sanitized evidence to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
