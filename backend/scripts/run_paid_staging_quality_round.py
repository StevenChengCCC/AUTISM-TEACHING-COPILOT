#!/usr/bin/env python3
"""Run one bounded, synthetic, paid-provider lesson-kit quality round.

This command intentionally stops before teacher/visual approval. It captures the
provider output for inspection so a failed or unsafe visual cannot be approved
automatically. Tokens, signed URLs, full prompts, and raw record text are never
written to the output directory.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
from http.client import RemoteDisconnected
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


CORE_TYPES = {"break_card", "first_then_board", "data_sheet"}
EXPECTED_COMPANIONS = {
    "blue_line_activity",
    "scenario_cards",
    "teacher_cue_card",
    "token_board",
    "visual_timer",
    "summary_template",
}
TERMINAL_JOBS = {"completed", "partially_complete", "failed"}
PLACEHOLDER_PATTERNS = (
    r"\bplaceholder\b",
    r"\bto be confirmed\b",
    r"\bteacher-confirmed reward\b",
    r"\bTBD\b",
    r"\blorem ipsum\b",
)
PROHIBITED_PATTERNS = (
    r"hand[- ]over[- ]hand",
    r"forced compliance",
    r"withhold(?:ing)? (?:a )?break",
    r"red angry face",
)


class RoundFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str, token: str, timeout: int = 90):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout

    def request(
        self,
        method: str,
        path_or_url: str,
        payload: dict[str, Any] | None = None,
        *,
        expect_json: bool = True,
    ) -> Any:
        url = (
            path_or_url
            if path_or_url.startswith(("https://", "http://"))
            else urljoin(self.base_url, path_or_url.lstrip("/"))
        )
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
        }
        # API routes use the private Cognito bearer. Absolute provider/object
        # storage URLs already carry their own bounded signature; adding a
        # second Authorization mechanism makes S3 reject an otherwise valid
        # download with HTTP 400.
        if not path_or_url.startswith(("https://", "http://")):
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    content = response.read()
                break
            except HTTPError as exc:
                # Parse only the API's intentionally privacy-safe error envelope;
                # never echo arbitrary HTML/provider bodies or compatibility payloads.
                safe_detail = ""
                try:
                    error = json.loads(exc.read())
                    code = str(error.get("code") or "").strip()
                    message = re.sub(
                        r"[\r\n\t]+", " ", str(error.get("message") or "")
                    ).strip()[:300]
                    if code or message:
                        safe_detail = f" ({code}: {message})"
                except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                    safe_detail = ""
                raise RoundFailure(
                    f"{method} {urlsplit(url).path} returned HTTP {exc.code}{safe_detail}"
                ) from exc
            except (URLError, RemoteDisconnected, TimeoutError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                reason = getattr(exc, "reason", exc)
                raise RoundFailure(
                    f"{method} {urlsplit(url).path} failed: {reason.__class__.__name__}"
                ) from exc
        if not expect_json:
            return content
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RoundFailure(
                f"{method} {urlsplit(url).path} returned invalid JSON"
            ) from exc


def _profile_factor(
    factor_id: str,
    category: str,
    value: str,
    *,
    constraints: list[str] | None = None,
    status: str = "confirmed_current",
) -> dict[str, Any]:
    return {
        "id": factor_id,
        "category": category,
        "label": factor_id.replace("-", " ").title(),
        "value": value,
        "status": status,
        "confidence": 0.99,
        "sourceEvidence": "Synthetic acceptance fixture statement.",
        "sourceRecordId": "synthetic-record-quality-loop",
        "instructionalImplication": value,
        "generationConstraints": constraints or [],
        "teacherReviewed": status == "confirmed_current",
    }


def _normalized_profile() -> dict[str, Any]:
    factors = [
        _profile_factor(
            "communication-speech-aac",
            "communication",
            "Speech and AAC are accepted equally.",
            constraints=["accept_response_mode=speech", "accept_response_mode=AAC"],
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
            "Independent opportunity, visual cue, gesture, then brief verbal model.",
        ),
        _profile_factor(
            "no-hand-over-hand",
            "prohibited_item",
            "Hand-over-hand prompting is prohibited.",
        ),
        _profile_factor(
            "short-blocks",
            "attention",
            "Use teaching blocks no longer than six minutes with a visible endpoint.",
            constraints=["maximum_teaching_block_minutes=6"],
        ),
        _profile_factor(
            "five-bus-tokens",
            "reinforcement",
            "Use exactly five bus tokens.",
            constraints=["token_count=5"],
        ),
        _profile_factor(
            "transit-map-reward",
            "reinforcement",
            "Two-minute transit-map break.",
        ),
        _profile_factor(
            "specific-praise",
            "reinforcement",
            "Specific praise: You asked for a break by yourself.",
        ),
        _profile_factor(
            "blue-line-interest",
            "current_interest",
            "Blue transit lines and city-bus station maps.",
        ),
        _profile_factor(
            "first-then-return",
            "transition",
            "Use First-Then, a one-minute visual warning, and show First-Then again on return.",
        ),
        _profile_factor(
            "two-minute-break",
            "regulation",
            "Honor a 2-minute break request with a visible timer.",
            constraints=["break_duration_minutes=2"],
        ),
        _profile_factor(
            "low-clutter",
            "visual_access",
            "Use high-contrast, low-clutter pages with blue as an organizing accent.",
        ),
        _profile_factor(
            "four-choices-maximum",
            "visual_access",
            "Show no more than four primary choices.",
            constraints=["maximum_response_options_per_page=4"],
        ),
        _profile_factor(
            "no-audio",
            "sensory",
            "No audio prompts, sound effects, applause, or alarms.",
        ),
        _profile_factor(
            "motor-access",
            "motor_access",
            "Do not require handwriting or fine-motor cutting.",
        ),
        _profile_factor(
            "three-contexts",
            "generalization",
            "Practice across transit-map activity to table work, art activity to cleanup, and free choice to shared reading.",
            constraints=["minimum_generalization_contexts=3"],
        ),
        _profile_factor(
            "spanish-labels",
            "unresolved_assumption",
            "Whether paired Spanish labels improve comprehension.",
            status="unconfirmed",
        ),
        _profile_factor(
            "image-style",
            "unresolved_assumption",
            "Whether photographs or line drawings are preferred.",
            status="unconfirmed",
        ),
        _profile_factor(
            "food-reward",
            "reinforcement",
            "Food rewards are not approved.",
            status="not_approved",
        ),
    ]
    return {
        "learnerId": "synthetic-pending",
        "age": 11,
        "factors": factors,
        "confirmedFactorIds": [
            item["id"]
            for item in factors
            if item["status"] == "confirmed_current"
        ],
        "unconfirmedFactorIds": [
            item["id"] for item in factors if item["status"] == "unconfirmed"
        ],
        "historicalFactorIds": [],
        "excludedFactorIds": [
            item["id"]
            for item in factors
            if item["status"] == "not_approved"
            or item["category"] == "prohibited_item"
        ],
        "blockingIssues": [],
        "summary": {
            "communication": "Speech and AAC",
            "supports": ["First-Then", "five-second wait", "visible break timer"],
            "currentInterests": ["Blue transit lines and city buses"],
            "learningFormat": "Brief visual teaching blocks",
            "keyTeachingNotes": ["Honor break requests", "No physical prompting"],
        },
    }


def _synthetic_profile(run_suffix: str) -> dict[str, Any]:
    return {
        "code": f"SYN-PROMO-{run_suffix}",
        "age": 11,
        "tags": ["Synthetic acceptance case", "Speech and AAC"],
        "interests": ["city buses", "transit maps", "Blue Line stations"],
        "supportNeeds": [
            "five seconds of processing time before prompting",
            "a visible endpoint for table work",
            "a predictable two-minute break and concrete return cue",
        ],
        "reinforcementPreferences": [
            "earn exactly five bus tokens for a two-minute transit-map break"
        ],
        "communicationMode": "Speech or a 2-by-3 AAC grid are both valid",
        "attentionProfile": "Works best in short, visible chunks with a clear finish",
        "notes": "Fully synthetic promotional acceptance profile. No real learner data.",
        "strengths": ["matches transit symbols", "follows visual routes"],
        "sensoryPreferences": ["quiet visual supports", "no flashing graphics"],
        "knownChallenges": [
            "may leave table work without a functional break request",
            "transition from preferred transit-map activities to shared reading",
        ],
        "promptingPreferences": [
            "wait five seconds",
            "least-to-most: visual cue, gesture, brief verbal model",
            "fade prompts across successful opportunities",
        ],
        "currentGoals": [
            "independently request a break with speech or AAC and return after two minutes"
        ],
        "readingLevel": "short familiar phrases with a paired symbol",
        "activityDurationPreference": "8-12 minute lesson with short practice blocks",
        "responseOptions": ["speech", "AAC selection", "pointing to the break card"],
        "receptiveSupports": ["one-step directions", "First-Then visual"],
        "expressiveSupports": ["exact phrase: Break, please", "AAC response accepted"],
        "environmentalConsiderations": [
            "table work",
            "art activity to cleanup",
            "free choice to shared reading",
        ],
        "effectiveSupports": [
            "five bus tokens",
            "two-minute visual timer",
            "concrete return-to-table cue",
        ],
        "ineffectiveSupports": [
            "repeating directions rapidly",
            "generic praise without a visible endpoint",
        ],
        "independenceProfile": (
            "Independent means selecting AAC or saying Break, please before leaving, "
            "after a five-second wait and without a model prompt."
        ),
        "emergingSkills": ["requesting a break before leaving an activity"],
        "generalizationProfile": "Practice across three familiar classroom transitions",
        "breakPreferences": ["two minutes with a transit map, then return to table work"],
        "classroomBarriers": ["long verbal directions", "unclear finishing points"],
        "normalizedProfile": _normalized_profile(),
        "profileReviewStatus": "draft",
    }


def _teacher_request() -> str:
    return (
        "Create a short, age-respectful lesson that teaches the learner to say or select "
        "'Break, please' before leaving table work. Accept speech and AAC equally, wait "
        "five seconds before prompting, and never use hand-over-hand prompting. Use a "
        "Complete the Blue Line transit-map activity with distinct station visuals, a "
        "concrete First-Then board, exactly five bus tokens, a separate transit-map reward "
        "image, a two-minute timer, and three real classroom transition scenarios. I only "
        "want Break Card, First-Then Board, and Data Sheet as my selected core materials; "
        "add only the companions required to make the lesson executable."
    )


def _choose_options(question: dict[str, Any]) -> tuple[list[str], str]:
    field = question.get("field")
    options = [item for item in question.get("options", []) if item.get("supported", True)]
    if field == "goalText":
        return [], (
            "Independently request a two-minute break by saying or selecting "
            "'Break, please' before leaving table work."
        )
    if field == "scenarios":
        recommended = [item["id"] for item in options if item.get("recommended")]
        remaining = [
            item["id"] for item in options if item["id"] not in recommended
        ]
        selected = [*recommended, *remaining][:3]
        return selected, ""
    if field == "selectedMaterials":
        selected: list[str] = []
        for item in options:
            value = " ".join(
                str(item.get(key, "")) for key in ("label", "value", "description")
            ).casefold()
            if any(
                phrase in value
                for phrase in ("break card", "first-then", "first then", "data sheet")
            ):
                selected.append(item["id"])
        return selected, "" if selected else "Break Card, First-Then Board, Data Sheet"
    recommended = [item["id"] for item in options if item.get("recommended")]
    limit = question.get("maxSelections") or len(recommended) or 1
    if recommended:
        return recommended[:limit], ""
    if options and question.get("required"):
        return [options[0]["id"]], ""
    return [], ""


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for child in value.values():
            result.extend(_flatten_strings(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_flatten_strings(child))
        return result
    return []


def _collect_visual_ids(materials: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for material in materials:
        plan = material.get("visualAssetPlan") or {}
        for item in plan.get("visualItems", []):
            if item.get("assetId"):
                result.add(item["assetId"])
    return result


def _save_assets(
    client: ApiClient,
    materials: list[dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    target_ids = _collect_visual_ids(materials)
    if not target_ids:
        return []
    assets = client.request("GET", "/api/v2/image-assets")
    saved: list[dict[str, Any]] = []
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        if asset.get("id") not in target_ids:
            continue
        data: bytes | None = None
        image_base64 = asset.get("imageBase64")
        image_url = asset.get("imageUrl")
        if isinstance(image_base64, str) and image_base64:
            data = base64.b64decode(image_base64)
        elif isinstance(image_url, str) and image_url:
            data = client.request("GET", image_url, expect_json=False)
        if not data:
            continue
        digest = hashlib.sha256(data).hexdigest()
        suffix = ".png"
        if data.startswith(b"\xff\xd8"):
            suffix = ".jpg"
        elif data.startswith(b"RIFF") and b"WEBP" in data[:16]:
            suffix = ".webp"
        file_name = f"{asset['id']}-{digest[:12]}{suffix}"
        (image_dir / file_name).write_bytes(data)
        saved.append(
            {
                "assetId": asset["id"],
                "file": f"images/{file_name}",
                "sha256": digest,
                "bytes": len(data),
                "title": asset.get("title", ""),
                "concept": asset.get("concept", ""),
                "altText": asset.get("altText", ""),
                "approved": asset.get("approved", False),
                "safetyStatus": asset.get("safetyStatus"),
                "sourceType": asset.get("sourceType"),
            }
        )
    return saved


def _save_deterministic_fallbacks(
    materials: list[dict[str, Any]], output_dir: Path
) -> list[dict[str, Any]]:
    saved: list[dict[str, Any]] = []
    target = output_dir / "fallbacks"
    for material in materials:
        for index, item in enumerate(
            (material.get("content") or {}).get("visualItems", [])
        ):
            image_url = str(item.get("imageUrl") or "")
            prefix = "data:image/svg+xml;base64,"
            if item.get("imageSourceType") != "internal" or not image_url.startswith(prefix):
                continue
            data = base64.b64decode(image_url[len(prefix) :])
            digest = hashlib.sha256(data).hexdigest()
            target.mkdir(parents=True, exist_ok=True)
            file_name = (
                f"{material.get('type', 'material')}-{index + 1}-{digest[:12]}.svg"
            )
            (target / file_name).write_bytes(data)
            saved.append(
                {
                    "materialId": material.get("id"),
                    "materialType": material.get("type"),
                    "visualId": item.get("id"),
                    "label": item.get("label"),
                    "file": f"fallbacks/{file_name}",
                    "sha256": digest,
                    "bytes": len(data),
                    "visible": True,
                }
            )
    return saved


def _renderable_package_text(package: dict[str, Any]) -> str:
    materials = []
    for material in package.get("materials", []):
        material_spec = material.get("materialSpec") or {}
        materials.append(
            {
                "title": material.get("title"),
                "content": material.get("content"),
                "typedContent": material_spec.get("content"),
                "teacherDirections": (material.get("specification") or {}).get(
                    "teacherDirections"
                ),
            }
        )
    renderable = {
        "lessonBrief": package.get("lessonBrief"),
        "summaryTemplate": package.get("summaryTemplate"),
        "teachingFlow": package.get("teachingFlow"),
        "preparationChecklist": package.get("preparationChecklist"),
        "materials": materials,
    }
    return "\n".join(_flatten_strings(renderable))


def _contains_unsafe_directive(text: str) -> bool:
    for pattern in PROHIBITED_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            window = text[max(0, match.start() - 48) : match.end() + 48].casefold()
            safe_cues = (
                "never",
                "no ",
                "do not",
                "avoid",
                "prohibit",
                "not allowed",
                "without",
            )
            if any(cue in window for cue in safe_cues):
                continue
            return True
    return False


def _quality_report(
    chat: dict[str, Any],
    package: dict[str, Any],
    job: dict[str, Any],
    assets: list[dict[str, Any]],
    fallbacks: list[dict[str, Any]],
) -> dict[str, Any]:
    materials = package.get("materials", [])
    material_types = {item.get("type") for item in materials}
    joined = _renderable_package_text(package)
    lower = joined.casefold()
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, evidence: str) -> None:
        checks.append({"id": check_id, "passed": bool(passed), "evidence": evidence})

    metadata = chat.get("generationMetadata") or {}
    check(
        "paid_text_provider",
        metadata.get("outputSource") == "provider",
        f"provider={metadata.get('provider') or 'unknown'}; model={metadata.get('model') or 'unknown'}",
    )
    check("selected_core_preserved", CORE_TYPES <= material_types, ", ".join(sorted(material_types)))
    check(
        "required_companions_present",
        EXPECTED_COMPANIONS <= material_types,
        ", ".join(sorted(EXPECTED_COMPANIONS - material_types)) or "all present",
    )
    check("not_every_catalog_item", len(materials) <= 12, f"materialCount={len(materials)}")
    check("exact_break_wording", "break, please" in lower, "exact phrase search")
    check("speech_and_aac", "speech" in lower and "aac" in lower, "modality search")
    check("five_second_wait", "5 seconds" in lower or "five seconds" in lower, "wait-time search")
    check("exactly_five_tokens", "five bus tokens" in lower or "5 bus tokens" in lower, "token search")
    check("transit_reward", "transit-map" in lower or "transit map" in lower, "reward-theme search")
    check("no_placeholders", not any(re.search(pattern, joined, re.I) for pattern in PLACEHOLDER_PATTERNS), "placeholder scan")
    check("no_prohibited_language", not _contains_unsafe_directive(joined), "unsafe directive scan with explicit prohibition handling")
    specs_pass = all(
        ((item.get("materialSpec") or {}).get("semanticValidation") or {}).get("status") == "passed"
        and ((item.get("materialSpec") or {}).get("safetyValidation") or {}).get("status") == "passed"
        for item in materials
    )
    check("semantic_and_safety_validation", specs_pass, "all current material revisions")
    check("generation_job_completed", job.get("status") == "completed", f"status={job.get('status')}")
    provider_assets = [item for item in assets if item.get("sourceType") == "generated"]
    check("multiple_paid_visuals", len(provider_assets) >= 3, f"generatedAssetCount={len(provider_assets)}")
    hashes = [item["sha256"] for item in provider_assets]
    check("visuals_not_duplicated", len(hashes) == len(set(hashes)), f"unique={len(set(hashes))}/{len(hashes)}")
    check(
        "visuals_need_teacher_review",
        all(not item.get("approved") for item in provider_assets),
        "capture stops before approval",
    )
    check(
        "visible_deterministic_fallbacks",
        all(item.get("visible") and item.get("bytes", 0) > 0 for item in fallbacks),
        f"savedFallbackCount={len(fallbacks)}",
    )
    return {
        "overallStatus": "PASS" if all(item["passed"] for item in checks) else "NEEDS_REVIEW",
        "checks": checks,
        "materialCount": len(materials),
        "visualCount": len(assets),
        "paidVisualCount": len(provider_assets),
        "fallbackVisualCount": len(fallbacks),
        "materialTypes": sorted(str(item) for item in material_types if item),
    }


def _safe_package_snapshot(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": package.get("id"),
        "learnerId": package.get("learnerId"),
        "draftId": package.get("draftId"),
        "version": package.get("version"),
        "status": package.get("status"),
        "validationStatus": package.get("validationStatus"),
        "goal": package.get("goal"),
        "duration": package.get("duration"),
        "theme": package.get("theme"),
        "lessonBrief": package.get("lessonBrief"),
        "teachingFlow": package.get("teachingFlow", []),
        "preparationChecklist": package.get("preparationChecklist", []),
        "qualityScore": package.get("qualityScore"),
        "safetyReview": package.get("safetyReview"),
        "lessonSpec": package.get("lessonSpec"),
        "packageContentPlan": package.get("packageContentPlan"),
        "materials": package.get("materials", []),
        "generationStatus": package.get("generationStatus"),
        "generationMetadata": package.get("generationMetadata"),
        "aiProvider": package.get("aiProvider"),
        "fallbackUsed": package.get("fallbackUsed"),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paid staging lesson-kit quality round",
        "",
        f"- Status: **{report['quality']['overallStatus']}**",
        f"- Round: {report['round']}",
        f"- Materials: {report['quality']['materialCount']}",
        f"- Saved visuals: {report['quality']['visualCount']}",
        f"- Paid generated visuals: {report['quality']['paidVisualCount']}",
        f"- Saved deterministic fallbacks: {report['quality']['fallbackVisualCount']}",
        "- Synthetic data only: yes",
        "- Visual approval performed: no (inspection required)",
        "",
        "## Deterministic checks",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for item in report["quality"]["checks"]:
        evidence = str(item["evidence"]).replace("|", "\\|")
        lines.append(f"| {item['id']} | {'PASS' if item['passed'] else 'FAIL'} | {evidence} |")
    lines.extend(
        [
            "",
            "## Next gate",
            "",
            "Inspect every saved visual for semantic correctness, distinct scenarios, no embedded instructional text, age respectfulness, and prohibited imagery before any review or approval call.",
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
        chat = client.request(
            "GET", f"/api/v2/lesson-chat/{args.resume_conversation_id}"
        )
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
            "POST",
            "/api/v2/lesson-chat/start",
            {"learnerId": learner["id"], "resumeExisting": False},
        )
        chat = client.request(
            "POST",
            "/api/v2/lesson-chat/message",
            {
                "conversationId": chat["conversationId"],
                "learnerId": learner["id"],
                "message": _teacher_request(),
            },
        )
    if (chat.get("generationMetadata") or {}).get("outputSource") != "provider":
        raise RoundFailure("Lesson interpretation did not come from the configured paid provider")

    if args.resume_job_id:
        if not args.resume_conversation_id:
            raise RoundFailure("--resume-job-id requires --resume-conversation-id")
        job = client.request("GET", f"/api/v2/generation-jobs/{args.resume_job_id}")
        if not job.get("packageId"):
            raise RoundFailure("The persisted generation job has no package yet")
        package = client.request(
            "GET", f"/api/v2/lesson-packages/{job['packageId']}"
        )
    else:
        for question in list(chat.get("questions", [])):
            selected, custom = _choose_options(question)
            if not selected and not custom and question.get("required"):
                raise RoundFailure(f"No safe answer available for required question {question.get('field')}")
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
        for optional in list(plan.get("optionalEnrichments", [])):
            if not optional.get("defaultIncluded"):
                continue
            chat = client.request(
                "PATCH",
                f"/api/v2/lesson-chat/{chat['conversationId']}/content-plan",
                {
                    "action": "set_optional",
                    "materialType": optional["materialType"],
                    "included": False,
                    "expectedDraftVersion": chat["draft"]["version"],
                },
            )

        if not chat.get("canGenerate"):
            raise RoundFailure("Teacher-confirmed draft is not generation-ready")
        package = client.request("POST", "/api/v2/lesson-packages/generate", chat["draft"])
        job = client.request("GET", f"/api/v2/lesson-packages/{package['id']}/generation-job")
    if job.get("cost", {}).get("estimatedVisualCount", 0) > args.max_visuals:
        raise RoundFailure(
            f"Server estimated {job['cost']['estimatedVisualCount']} visuals, exceeding --max-visuals"
        )
    deadline = time.monotonic() + args.max_wait_seconds
    while job.get("status") not in TERMINAL_JOBS:
        if time.monotonic() >= deadline:
            raise RoundFailure("Generation job exceeded the bounded wait time")
        time.sleep(args.poll_seconds)
        job = client.request("GET", f"/api/v2/generation-jobs/{job['jobId']}")

    package = client.request("GET", f"/api/v2/lesson-packages/{package['id']}")
    assets = _save_assets(client, package.get("materials", []), args.output_dir)
    fallbacks = _save_deterministic_fallbacks(
        package.get("materials", []), args.output_dir
    )
    quality = _quality_report(chat, package, job, assets, fallbacks)
    report = {
        "schemaVersion": 1,
        "round": args.round,
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
            "artifacts": job.get("artifacts", []),
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
    parser.add_argument("--round", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--max-visuals", type=int, default=12)
    parser.add_argument("--max-wait-seconds", type=int, default=1200)
    parser.add_argument("--request-timeout", type=int, default=90)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument(
        "--resume-conversation-id",
        help="Resume a persisted synthetic teacher-selection state without repeating lesson interpretation.",
    )
    parser.add_argument(
        "--resume-job-id",
        help="Continue polling and capture an existing durable synthetic generation job.",
    )
    parser.add_argument("--confirm-paid-ai", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, RoundFailure, ValueError) as exc:
        if args.output_dir.is_dir() and not (args.output_dir / "report.json").exists():
            (args.output_dir / "failure.md").write_text(
                "# Paid staging quality round failed\n\n"
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
        f"{report['quality']['paidVisualCount']} paid visuals"
    )
    print(f"Saved sanitized evidence to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
