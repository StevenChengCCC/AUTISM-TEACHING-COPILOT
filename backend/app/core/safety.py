from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyVerdict:
    requires_bcba: bool
    category: str | None
    matched_terms: list[str]


# BCBA-reviewable deterministic English deny-list. Keep conservative: these terms
# route behavior-reduction goals out of automated lesson generation.
PROBLEM_BEHAVIOR_REDUCTION_PATTERNS: dict[str, list[str]] = {
    "self_injury": [
        r"\bself[-\s]?injur(?:y|ious)\b",
        r"\bhead\s*banging\b",
        r"\bskin\s*picking\b",
        r"\bself\s*harm\b",
    ],
    "aggression": [
        r"\baggression\b",
        r"\baggressive\b",
        r"\bhitting\b",
        r"\bhit\s+(?:peers?|others?|teacher|adult|classmates?)\b",
        r"\bbiting\b",
        r"\bbite\s+(?:peers?|others?|teacher|adult|classmates?)\b",
        r"\bkicking\b",
        r"\bscratching\b",
        r"\bpinching\b",
    ],
    "elopement": [
        r"\belopement\b",
        r"\bbolting\b",
        r"\brun(?:ning)?\s*away\b",
        r"\bleav(?:e|ing)\s+(?:the\s+)?(?:classroom|room|area)\b",
    ],
    "property_destruction": [
        r"\bproperty\s+destruction\b",
        r"\bdestroy(?:ing)?\s+(?:property|materials|items)\b",
        r"\bthrow(?:ing)?\s+(?:objects|items|materials)\b",
        r"\bbreak(?:ing)?\s+(?:objects|items|materials|property)\b",
    ],
    "pica": [
        r"\bpica\b",
        r"\beingest(?:ing)?\s+non[-\s]?food\b",
        r"\beat(?:ing)?\s+non[-\s]?food\b",
    ],
    "restraint": [
        r"\brestraint\b",
        r"\bphysical\s+hold\b",
        r"\bmanual\s+hold\b",
    ],
    "behavior_reduction": [
        r"\b(?:reduce|eliminate|extinguish|decrease|stop)\b.{0,40}\bbehaviou?r\b",
        r"\bbehaviou?r\b.{0,40}\b(?:reduction|elimination|extinction)\b",
    ],
}


def classify_goal_safety(
    target_skill: str | None,
    concept: str | None,
    notes: str | None,
    behavior_notes: str | None = None,
) -> SafetyVerdict:
    # The hard BCBA block is scoped to the goal's own definition
    # (target_skill + concept + notes). ``behavior_notes`` is descriptive
    # background about the child and is intentionally excluded from the
    # deny-list scan: phrases like "no self-injury, no aggression" must not
    # block a benign acquisition goal. A real reduction goal (e.g.
    # "reduce hitting peers") still lives in target_skill/notes and blocks.
    text = " ".join(
        value.strip()
        for value in [target_skill, concept, notes]
        if value and value.strip()
    )
    if not text:
        return SafetyVerdict(False, None, [])

    matches_by_category: dict[str, list[str]] = {}
    for category, patterns in PROBLEM_BEHAVIOR_REDUCTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                matches_by_category.setdefault(category, []).append(pattern)

    if not matches_by_category:
        return SafetyVerdict(False, None, [])

    category, matched_terms = next(iter(matches_by_category.items()))
    return SafetyVerdict(True, category, matched_terms)
