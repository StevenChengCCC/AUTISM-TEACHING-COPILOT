from __future__ import annotations

import base64
from hashlib import sha256
import re

from app.core.exceptions import ValidationError
from app.schemas.v2_dto import (
    ChoiceBoardSpec,
    CommunicationCardSpec,
    ConceptExemplarCardsSpec,
    FirstThenBoardSpec,
    GoalSpecificDataSheetSpec,
    LessonSummarySpec,
    MaterialSpec,
    MaterialValidationIssue,
    PersonalizedInstructionalActivitySpec,
    RegulationScaleSpec,
    ScenarioCardsSpec,
    TokenBoardSpec,
    VisualAssetPlan,
    VisualAssetPlanItem,
    VisualTimerSpec,
)


class V2VisualAssetPlanService:
    """Derive instructional visuals from typed MaterialSpec semantics.

    The plan owns semantic identity and generation policy. ``content.visualItems``
    remains a temporary projection for the existing printable renderer.
    """

    duplicate_policy = (
        "Assets may not be reused across different semantic keys. The token master "
        "may be repeated only by deterministic token-instance items that explicitly "
        "reference its semantic key."
    )

    def build(self, material_spec: MaterialSpec) -> VisualAssetPlan:
        items = self._items(material_spec)
        return VisualAssetPlan(
            materialId=material_spec.id,
            materialRevision=material_spec.revision,
            visualItems=items,
            minimumRequiredVisuals=sum(item.required for item in items),
            maximumAllowedVisuals=len(items),
            duplicatePolicy=self.duplicate_policy,
            textInImageAllowed=False,
        )

    def validate(
        self, plan: VisualAssetPlan, material_spec: MaterialSpec
    ) -> list[MaterialValidationIssue]:
        issues: list[MaterialValidationIssue] = []

        def add(path: str, code: str, message: str, remediation: str) -> None:
            issues.append(MaterialValidationIssue(
                fieldPath=path, code=code, message=message, remediation=remediation
            ))

        if plan.material_id != material_spec.id or plan.material_revision != material_spec.revision:
            add(
                "visualAssetPlan.materialRevision", "stale_visual_plan",
                "The visual plan does not match the current material revision.",
                "Rebuild the visual plan from the current MaterialSpec.",
            )
            return issues

        expected = self.build(material_spec)
        expected_keys = [(item.role, item.semantic_key) for item in expected.visual_items]
        actual_keys = [(item.role, item.semantic_key) for item in plan.visual_items]
        if actual_keys != expected_keys:
            add(
                "visualAssetPlan.visualItems", "visual_count_or_semantics_mismatch",
                "Visual count or semantic roles do not match the typed material content.",
                "Rebuild the plan so every scenario, choice, step, token, and task component has its required visual.",
            )

        if plan.minimum_required_visuals != sum(item.required for item in plan.visual_items):
            add(
                "visualAssetPlan.minimumRequiredVisuals", "wrong_required_visual_count",
                "The required visual count is inconsistent with the planned items.",
                "Recalculate the count from required visual items.",
            )

        seen_semantics: set[tuple[str, str]] = set()
        assets: dict[str, str] = {}
        prohibited = [value.casefold() for value in material_spec.design_constraints.prohibited_visual_features]
        for index, item in enumerate(plan.visual_items):
            path = f"visualAssetPlan.visualItems[{index}]"
            identity = (item.role, item.semantic_key)
            if identity in seen_semantics and not item.design_constraints.get("reusesTokenSemanticKey"):
                add(path, "duplicate_semantic_visual", "A semantic visual is duplicated.", "Use one distinct semantic key per instructional visual.")
            seen_semantics.add(identity)

            positive_prompt = (item.prompt or "").casefold()
            if item.generation_method == "ai_generated":
                embedded_text_terms = (
                    "include text", "show text", "write the", "words reading",
                    "label reading", "caption reading", "display the phrase",
                )
                if any(term in positive_prompt for term in embedded_text_terms):
                    add(path + ".prompt", "embedded_instructional_text_requested", "The AI prompt requests embedded instructional text.", "Keep all labels as renderer text outside the image.")
                if not item.negative_prompt or "text" not in item.negative_prompt.casefold():
                    add(path + ".negativePrompt", "missing_no_text_constraint", "The image request does not explicitly prohibit embedded text.", "Add text, letters, numerals, logos, and watermarks to the negative prompt.")
            if any(value and value in positive_prompt for value in prohibited):
                add(path + ".prompt", "prohibited_imagery_requested", "The image request contains a prohibited visual feature.", "Remove the prohibited feature and rebuild the request.")
            if not item.alt_text.strip() or not item.visible_label.strip():
                add(path + ".altText", "missing_semantic_alt_text", "The visual lacks aligned visible-label or alternative-text metadata.", "Describe the concrete visible content and the task it represents.")
            if item.asset_id:
                prior_key = assets.get(item.asset_id)
                reuse_key = item.design_constraints.get("reusesTokenSemanticKey")
                if prior_key and prior_key != item.semantic_key and not reuse_key:
                    add(path + ".assetId", "cross_semantic_asset_reuse", "One asset is reused for unrelated semantic roles.", "Create or select a distinct asset for this semantic key.")
                assets[item.asset_id] = item.semantic_key

        return issues

    def require_valid(self, plan: VisualAssetPlan, material_spec: MaterialSpec) -> VisualAssetPlan:
        issues = self.validate(plan, material_spec)
        if issues:
            raise ValidationError(
                "VisualAssetPlan semantic validation failed",
                payload={"issues": [item.model_dump(mode="json", by_alias=True) for item in issues]},
            )
        return plan

    def approval_blockers(self, plan: VisualAssetPlan) -> list[str]:
        blockers: list[str] = []
        for item in plan.visual_items:
            usable_fallback = bool(item.fallback_asset_id)
            if item.required and item.status == "failed":
                blockers.append(f"{item.visible_label}: required visual failed and requires teacher recovery")
            if item.required and item.status in {"planned", "generating"} and not usable_fallback:
                blockers.append(f"{item.visible_label}: required visual is not ready")
            if item.required and item.review_status == "rejected" and not usable_fallback:
                blockers.append(f"{item.visible_label}: required visual was rejected with no fallback")
        return blockers

    def to_renderer_items(self, plan: VisualAssetPlan) -> list[dict]:
        result: list[dict] = []
        for item in plan.visual_items:
            constraints = item.design_constraints
            quantity = constraints.get("quantity")
            fallback = item.fallback_asset_id
            image_url = self.deterministic_svg_data_url(item) if fallback else None
            result.append({
                "id": item.id,
                "label": item.visible_label,
                "role": item.role,
                "semanticKey": item.semantic_key,
                "instructionalPurpose": item.instructional_purpose,
                "required": item.required,
                "generationMethod": item.generation_method,
                "designConstraints": item.design_constraints,
                "concept": constraints.get("concept", item.visible_label),
                "prompt": item.prompt,
                "imageAltText": item.alt_text,
                "imageAssetId": item.asset_id or fallback,
                "imageUrl": image_url,
                "imageBase64": None,
                "imageSourceType": "internal" if fallback else None,
                "imageLicenseInfo": "Deterministic application SVG" if fallback else None,
                "imageSafetyStatus": "ready" if fallback else "needs_review",
                "generationStatus": "ready" if fallback else item.status,
                **({"quantity": quantity} if isinstance(quantity, int) else {}),
            })
        return result

    @staticmethod
    def deterministic_svg_data_url(item: VisualAssetPlanItem) -> str:
        kind = str(item.design_constraints.get("fallbackKind") or item.role)
        accent = str(item.design_constraints.get("accentColor") or "#2563eb")
        concept = " ".join(
            str(item.design_constraints.get("concept") or item.visible_label)
            .casefold()
            .replace("-", " ")
            .split()
        )
        identity = f"{item.semantic_key}|{concept}"
        digest = sha256(identity.encode("utf-8")).digest()
        secondary = ("#0f766e", "#7c3aed", "#c2410c", "#0369a1")[digest[0] % 4]
        if kind == "route":
            body = f'<path d="M18 78 C40 12 74 96 108 28 C130 4 148 38 142 72" fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round"/>'
        elif kind == "start":
            body = '<circle cx="80" cy="80" r="46" fill="#16a34a"/><path d="M62 50 L116 80 L62 110 Z" fill="white"/>'
        elif kind == "finish":
            body = '<rect x="38" y="38" width="84" height="84" rx="8" fill="white" stroke="#1f2937" stroke-width="4"/><path d="M42 42h38v38H42zm38 38h38v38H80z" fill="#1f2937"/>'
        elif kind == "timer":
            progress = float(item.design_constraints.get("progress", 0.5))
            dash = max(1, min(276, int(276 * progress)))
            body = f'<circle cx="80" cy="84" r="44" fill="#eef2ff" stroke="#cbd5e1" stroke-width="12"/><circle cx="80" cy="84" r="44" fill="none" stroke="{accent}" stroke-width="12" stroke-linecap="round" stroke-dasharray="{dash} 276" transform="rotate(-90 80 84)"/><path d="M64 20h32" stroke="#334155" stroke-width="8" stroke-linecap="round"/>'
        elif kind == "bus":
            body = f'<rect x="24" y="44" width="112" height="64" rx="16" fill="{accent}"/><rect x="38" y="56" width="34" height="22" rx="3" fill="white"/><rect x="82" y="56" width="34" height="22" rx="3" fill="white"/><circle cx="50" cy="112" r="12" fill="#334155"/><circle cx="110" cy="112" r="12" fill="#334155"/>'
        elif "art" in concept or "cleanup" in concept:
            body = f'<rect x="86" y="68" width="48" height="58" rx="8" fill="#e2e8f0" stroke="#475569" stroke-width="4"/><path d="M24 116 L76 42" stroke="{accent}" stroke-width="12" stroke-linecap="round"/><path d="M70 48 L82 30" stroke="{secondary}" stroke-width="18" stroke-linecap="round"/><path d="M94 58h32" stroke="#475569" stroke-width="7" stroke-linecap="round"/>'
        elif "reading" in concept or "book" in concept:
            body = f'<path d="M20 42 Q52 30 78 52 V126 Q50 106 20 116 Z" fill="#dbeafe" stroke="{accent}" stroke-width="5"/><path d="M140 42 Q108 30 82 52 V126 Q110 106 140 116 Z" fill="#ede9fe" stroke="{secondary}" stroke-width="5"/><path d="M80 50v76" stroke="#475569" stroke-width="4"/>'
        elif "table" in concept or "item" in concept or "task" in concept:
            body = f'<rect x="22" y="76" width="116" height="18" rx="6" fill="{accent}"/><path d="M38 94v34M122 94v34" stroke="#475569" stroke-width="9" stroke-linecap="round"/><rect x="36" y="42" width="22" height="22" rx="5" fill="{secondary}"/><rect x="69" y="42" width="22" height="22" rx="5" fill="#0f766e"/><rect x="102" y="42" width="22" height="22" rx="5" fill="#c2410c"/>'
        elif "transit" in concept or "route" in concept or "map" in concept:
            bend = 54 + digest[1] % 32
            body = f'<path d="M20 112 C44 {bend} 68 {bend} 88 54 S126 32 140 48" fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round"/><circle cx="24" cy="108" r="12" fill="white" stroke="{secondary}" stroke-width="6"/><circle cx="84" cy="58" r="12" fill="white" stroke="{secondary}" stroke-width="6"/><circle cx="136" cy="48" r="12" fill="white" stroke="{secondary}" stroke-width="6"/>'
        elif "break" in concept or "pause" in concept or "communication" in concept:
            body = f'<path d="M24 34h112v76H78l-26 20v-20H24z" fill="#eff6ff" stroke="{accent}" stroke-width="6"/><rect x="58" y="54" width="14" height="38" rx="5" fill="{secondary}"/><rect x="88" y="54" width="14" height="38" rx="5" fill="{secondary}"/>'
        else:
            offset = 36 + digest[1] % 28
            body = f'<rect x="28" y="28" width="104" height="104" rx="24" fill="#eff6ff" stroke="{accent}" stroke-width="6"/><circle cx="{offset}" cy="62" r="18" fill="{secondary}"/><path d="M42 116 Q80 {70 + digest[2] % 20} 118 116" fill="none" stroke="{accent}" stroke-width="12" stroke-linecap="round"/>'
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160" role="img">{body}</svg>'
        return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

    def _items(self, spec: MaterialSpec) -> list[VisualAssetPlanItem]:
        common_constraints = {
            "lowClutter": True,
            "literalNeutral": True,
            "largeTouchTargets": bool(spec.design_constraints.minimum_touch_target),
            "minimumTouchTarget": spec.design_constraints.minimum_touch_target,
            "layoutRequirements": spec.design_constraints.layout_requirements,
            "prohibitedVisualFeatures": spec.design_constraints.prohibited_visual_features,
            "prohibitedAudioFeatures": spec.design_constraints.prohibited_audio_features,
            "accentColor": "#2563eb",
        }

        def item(
            suffix: str, role: str, semantic_key: str, purpose: str, label: str,
            *, method: str, concept: str, required: bool = True,
            fallback_kind: str | None = "symbol", extra: dict | None = None,
        ) -> VisualAssetPlanItem:
            deterministic = method == "deterministic_svg"
            constraints = {**common_constraints, "concept": concept, **(extra or {})}
            if fallback_kind:
                constraints["fallbackKind"] = fallback_kind
            prompt = None
            negative = None
            if method == "ai_generated":
                literal_direction = (
                    " Depict the named classroom activity literally. The learner's "
                    "interest may affect accent color only; never replace the named "
                    "task, transition, or outcome with unrelated theme imagery."
                    if role in {"scenario", "first", "then", "task_item"}
                    else ""
                )
                if role == "concept_exemplar":
                    prompt = (
                        f"Create one realistic, literal, low-clutter instructional object image of {concept}. "
                        f"Show only the named object '{label}' on a plain light studio background. "
                        "Keep the whole object or requested cut form fully visible and centered."
                    )
                else:
                    prompt = (
                        f"Create one literal, neutral, low-clutter instructional illustration of {concept}. "
                        "Use one clear focal subject, a plain light background, and age-respectful concrete objects."
                        + literal_direction
                    )
                negative = (
                    "text, letters, numerals, captions, labels, logos, watermarks, decorative clutter, "
                    "identifiable learner, teacher, child, adult, person, hand, surrounding classroom scene, "
                    "unrequested objects, other fruit, exaggerated facial expressions, angry red faces"
                )
            fallback_id = f"deterministic:{spec.id}:{semantic_key}" if fallback_kind else None
            return VisualAssetPlanItem(
                id=f"{spec.id}-{suffix}", role=role, semanticKey=semantic_key,
                instructionalPurpose=purpose, required=required, generationMethod=method,
                prompt=prompt, negativePrompt=negative,
                altText=f"{label}: {concept}.", visibleLabel=label,
                profileFactorIds=spec.profile_factor_ids, designConstraints=constraints,
                status="ready" if deterministic else "planned",
                assetId=fallback_id if deterministic else None,
                fallbackAssetId=fallback_id,
            )

        if isinstance(spec, PersonalizedInstructionalActivitySpec):
            stations = spec.content.answer_key_or_expected_sequence or spec.content.required_components
            station_labels = [value for value in stations if self._clean(value)]
            if not station_labels:
                station_labels = [f"Task item {index + 1}" for index in range(spec.content.number_of_trials_or_items)]
            result = [
                item("route", "task_item", "route-background", "Organize the route-sequencing task.", "Route", method="deterministic_svg", concept="a simple organizing route", fallback_kind="route"),
                item("start", "task_item", "start-marker", "Show where the sequence begins.", "Start", method="deterministic_svg", concept="a clear start marker", fallback_kind="start"),
                item("finish", "task_item", "finish-marker", "Show where the sequence ends.", "Finish", method="deterministic_svg", concept="a clear finish marker", fallback_kind="finish"),
            ]
            for index, label in enumerate(station_labels):
                clean = self._clean(label)
                result.append(item(
                    f"station-{index + 1}", "task_item", f"station:{self._key(clean)}",
                    "Represent one distinct station card in the route sequence.", clean,
                    method="ai_generated", concept=f"the concrete activity station {clean}", fallback_kind="station",
                    extra={"stationIndex": index + 1},
                ))
            return result

        if isinstance(spec, ScenarioCardsSpec):
            return [item(
                f"scenario-{index + 1}", "scenario", f"scenario:{scenario.id}",
                "Depict this exact practice context and transition.", scenario.context,
                method="ai_generated",
                concept=(
                    f"a literal classroom scene for {scenario.context}; "
                    f"show the transition {scenario.trigger_or_transition}"
                ), fallback_kind="scenario",
                extra={"context": scenario.context, "transition": scenario.trigger_or_transition},
            ) for index, scenario in enumerate(spec.content.scenarios)]

        if isinstance(spec, ChoiceBoardSpec):
            return [item(
                f"choice-{index + 1}", "choice", f"choice:{choice.id}",
                "Represent this concrete selectable option.", choice.label,
                method="ai_generated", concept=choice.visual_description,
                fallback_kind="choice", extra={"choiceId": choice.id},
            ) for index, choice in enumerate(spec.content.choices)]

        if isinstance(spec, ConceptExemplarCardsSpec):
            return [item(
                f"concept-exemplar-{index + 1}",
                "concept_exemplar",
                f"concept-exemplar:{self._key(exemplar.label)}:{index + 1}",
                "Teach the same object concept across a meaningfully different real example.",
                exemplar.label,
                method="ai_generated",
                concept=exemplar.concept_description,
                fallback_kind=None,
                extra={
                    "targetLabel": exemplar.label,
                    "exemplarIndex": index + 1,
                    "objectOnly": True,
                },
            ) for index, exemplar in enumerate(spec.content.exemplars)]

        if isinstance(spec, FirstThenBoardSpec):
            return [
                item("first", "first", "first-task", "Represent the concrete FIRST task.", spec.content.first_task, method="ai_generated", concept=f"the concrete classroom task {spec.content.first_task}", fallback_kind="first"),
                item("then", "then", "then-outcome", "Represent the concrete THEN outcome.", spec.content.then_outcome, method="ai_generated", concept=f"the concrete earned outcome {spec.content.then_outcome}", fallback_kind="then"),
            ]

        if isinstance(spec, TokenBoardSpec):
            theme = self._clean(spec.content.token_symbol_or_theme)
            fallback_kind = "bus" if "bus" in theme.casefold() else "token"
            result = [item(
                "token-master", "token", "token-symbol", "Provide one reusable token symbol.", theme,
                method="ai_generated", concept=f"one isolated {theme} token symbol",
                fallback_kind=fallback_kind, extra={"tokenMaster": True},
            )]
            for index in range(spec.content.exact_token_count):
                result.append(item(
                    f"token-{index + 1}", "token", f"token-instance:{index + 1}",
                    "Render one position in the exact token count.", f"Token {index + 1}",
                    method="deterministic_svg", concept=f"repeated {theme} token instance",
                    fallback_kind=fallback_kind,
                    extra={"quantity": 1, "reusesTokenSemanticKey": "token-symbol"},
                ))
            result.append(item(
                "reward", "reward", "earned-reward", "Show the exact named earned reward.",
                spec.content.earned_reward, method="ai_generated",
                concept=spec.content.pictured_reward_description, fallback_kind="reward",
            ))
            return result

        if isinstance(spec, CommunicationCardSpec):
            return [item(
                "communication", "communication_symbol", "communication-symbol",
                "Provide a clear symbol for the communication action.",
                spec.content.exact_communication_phrase, method="ai_generated",
                concept=spec.content.symbol_description, fallback_kind="communication",
            )]

        if isinstance(spec, VisualTimerSpec):
            duration = spec.content.duration_minutes
            return [item(
                f"timer-{remaining}", "timer_state", f"timer-state:{remaining}",
                "Show a deterministic silent countdown state.",
                spec.content.end_label if remaining == 0 else f"{remaining} minutes remaining",
                method="deterministic_svg", concept="a silent visual timer state",
                fallback_kind="timer", extra={"remainingMinutes": remaining, "progress": remaining / duration},
            ) for remaining in range(duration, -1, -1)]

        if isinstance(spec, RegulationScaleSpec):
            return [item(
                f"level-{level.order}", "example", f"regulation-level:{level.order}",
                "Provide a neutral navigation symbol for this regulation option.", level.label,
                method="deterministic_svg", concept="a neutral regulation support indicator",
                fallback_kind="regulation",
            ) for level in spec.content.levels]

        if isinstance(spec, LessonSummarySpec) and "teacher cue" in spec.title.casefold():
            return [item(
                "teacher-reference", "teacher_reference", "teacher-reference",
                "Provide a navigation cue that identifies the teacher-facing prompt card.",
                "Teacher cue", method="deterministic_svg",
                concept="a neutral teacher reference symbol", fallback_kind="teacher",
            )]

        if isinstance(spec, (GoalSpecificDataSheetSpec, LessonSummarySpec)):
            return []
        return []

    @staticmethod
    def _clean(value: object) -> str:
        return " ".join(str(value).split())

    @staticmethod
    def _key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "item"
