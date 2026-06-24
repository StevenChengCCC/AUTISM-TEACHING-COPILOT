from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyVerdict:
    requires_bcba: bool
    category: str | None
    matched_terms: list[str]


# BCBA-reviewable deterministic deny-list. Keep conservative: these terms route
# behavior-reduction goals out of automated lesson generation.
PROBLEM_BEHAVIOR_REDUCTION_PATTERNS: dict[str, list[str]] = {
    "self_injury": [
        r"\bself[-\s]?injur(?:y|ious)\b",
        r"\bhead\s*banging\b",
        r"\bskin\s*picking\b",
        r"\bself\s*harm\b",
        r"自伤",
        r"自残",
        r"撞头",
        r"伤害自己",
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
        r"攻击",
        r"打人",
        r"咬人",
        r"踢人",
        r"抓人",
        r"伤人",
    ],
    "elopement": [
        r"\belopement\b",
        r"\bbolting\b",
        r"\brun(?:ning)?\s*away\b",
        r"\bleav(?:e|ing)\s+(?:the\s+)?(?:classroom|room|area)\b",
        r"逃跑",
        r"跑离",
        r"离开教室",
        r"冲出",
        r"走失",
    ],
    "property_destruction": [
        r"\bproperty\s+destruction\b",
        r"\bdestroy(?:ing)?\s+(?:property|materials|items)\b",
        r"\bthrow(?:ing)?\s+(?:objects|items|materials)\b",
        r"\bbreak(?:ing)?\s+(?:objects|items|materials|property)\b",
        r"破坏财物",
        r"破坏物品",
        r"摔东西",
        r"扔东西",
    ],
    "pica": [
        r"\bpica\b",
        r"\beingest(?:ing)?\s+non[-\s]?food\b",
        r"\beat(?:ing)?\s+non[-\s]?food\b",
        r"异食",
        r"乱吃",
        r"吃非食物",
    ],
    "restraint": [
        r"\brestraint\b",
        r"\bphysical\s+hold\b",
        r"\bmanual\s+hold\b",
        r"约束",
        r"身体限制",
        r"肢体限制",
    ],
    "behavior_reduction": [
        r"\b(?:reduce|eliminate|extinguish|decrease|stop)\b.{0,40}\bbehaviou?r\b",
        r"\bbehaviou?r\b.{0,40}\b(?:reduction|elimination|extinction)\b",
        r"(?:减少|降低|消除|停止|灭除).{0,20}行为",
        r"行为.{0,20}(?:减少|降低|消除|停止|灭除)",
    ],
}


def classify_goal_safety(
    target_skill: str | None,
    concept: str | None,
    notes: str | None,
    behavior_notes: str | None,
) -> SafetyVerdict:
    text = " ".join(
        value.strip()
        for value in [target_skill, concept, notes, behavior_notes]
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
