from __future__ import annotations

import re

PII_PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "phone": re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"),
    "birthday": re.compile(
        r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
    ),
    "address": re.compile(
        r"\b\d{1,6}\s+[A-Za-z0-9.'-]+\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Boulevard|Blvd)\b",
        re.I,
    ),
}


def scan_pii(text: str | None) -> list[str]:
    if not text:
        return []
    return [name for name, pattern in PII_PATTERNS.items() if pattern.search(text)]


def is_pseudonymous_child_code(code: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{2,32}", code or ""))
