from __future__ import annotations

import re


def extract_concept_labels(goal_text: str, observable_response: str = "") -> list[str]:
    """Extract one or two concrete referents from a reviewed identification goal."""

    source = goal_text.strip() or observable_response.strip()
    if not source:
        return []
    normalized = " ".join(source.split())
    action = r"(?:identify|identifies|label|labels|name|names|recognize|recognizes)"
    patterns = (
        r"(?:pictures?|images?|photos?|objects?)\s+of\s+(.+?)(?:\s+when\b|\s+after\b|\s+from\b|[.;]|$)",
        rf"{action}(?:\s+(?:and|or)\s+{action})?\s+"
        rf"(?:(?:the\s+)?(?:pictures?|images?|photos?|objects?)\s+of\s+)?"
        rf"(?:the\s+)?(.+?)(?:\s+when\b|\s+after\b|\s+from\b|[.;]|$)",
    )
    captured = ""
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            captured = match.group(1)
            break
    if not captured:
        return []
    captured = re.sub(
        r"^(?:the\s+)?(?:pictures?|images?|photos?|objects?)\s+of\s+",
        "",
        captured,
        flags=re.IGNORECASE,
    )
    captured = re.sub(
        r"\b(?:across|using|with|during|in)\b.*$",
        "",
        captured,
        flags=re.IGNORECASE,
    )
    labels: list[str] = []
    for raw in re.split(r"\s*(?:,|/|\band\b|\bor\b)\s*", captured):
        label = re.sub(r"^(?:a|an|the)\s+", "", raw.strip(), flags=re.I)
        label = re.sub(r"\s+(?:picture|image|photo)s?$", "", label, flags=re.I)
        if not label or len(label.split()) > 4 or len(label) > 42:
            continue
        if (
            len(label) > 3
            and label.casefold().endswith("s")
            and not label.casefold().endswith(("ss", "us", "is"))
        ):
            label = label[:-1]
        display = label[:1].upper() + label[1:]
        if display.casefold() not in {item.casefold() for item in labels}:
            labels.append(display)
    return labels[:2]


def concept_exemplar_variations(labels: list[str]) -> list[dict[str, str]]:
    """Return an eight-image-bounded, meaningfully varied exemplar plan."""

    clean_labels = [" ".join(str(label).split()) for label in labels[:2] if str(label).strip()]
    single = (
        "as a common red whole example from the front",
        "as a naturally different green whole example from the side",
        "as a naturally different yellow whole example at a three-quarter angle",
        "cut cleanly in half so the inside and seeds are visible",
        "as several clean slices that still clearly show the same object",
        "as a small naturally shaped whole example viewed from above",
    )
    paired = (
        "as a common whole example from the front",
        "as a naturally different whole example from the side",
        "cut cleanly in half so the inside is visible",
        "from a clear three-quarter angle",
    )
    variations = single if len(clean_labels) == 1 else paired
    result: list[dict[str, str]] = []
    for label in clean_labels:
        for variation in variations:
            result.append(
                {
                    "label": label,
                    "concept": f"one isolated {label} {variation}",
                }
            )
    return result[:8]
