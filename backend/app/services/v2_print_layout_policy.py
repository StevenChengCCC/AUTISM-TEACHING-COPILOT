from __future__ import annotations

from dataclasses import dataclass

from app.schemas.v2_dto import PrintTextProfile


@dataclass(frozen=True)
class PrintLayoutPolicy:
    """Versioned, deterministic accessibility rules for printable lesson kits."""

    text_profile: PrintTextProfile
    teacher_body_points: float
    teacher_compact_points: float
    teacher_data_header_points: float
    learner_label_points: float
    learner_primary_points: float
    safe_margin_inches: float = 0.55
    minimum_writable_row_inches: float = 0.36
    high_contrast_required: bool = True
    color_only_signals_allowed: bool = False
    preserve_image_aspect_ratio: bool = True
    repeat_table_headers: bool = True
    keep_headings_with_next: bool = True


POLICIES: dict[PrintTextProfile, PrintLayoutPolicy] = {
    "standard": PrintLayoutPolicy(
        text_profile="standard",
        teacher_body_points=10,
        teacher_compact_points=8,
        teacher_data_header_points=7,
        learner_label_points=22,
        learner_primary_points=30,
    ),
    "large": PrintLayoutPolicy(
        text_profile="large",
        teacher_body_points=12,
        teacher_compact_points=11,
        teacher_data_header_points=10,
        learner_label_points=26,
        learner_primary_points=34,
        minimum_writable_row_inches=0.42,
    ),
}


def print_layout_policy(text_profile: PrintTextProfile) -> PrintLayoutPolicy:
    return POLICIES[text_profile]


_ASCII_REPLACEMENTS = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2192": "->",
        "\u2022": "-",
        "\u25a1": "[ ]",
        "\u00b7": "-",
    }
)


def normalize_print_text(value: object) -> str:
    """Use glyphs supported by the built-in PDF fonts and ASCII hyphens."""

    return str(value).translate(_ASCII_REPLACEMENTS)
