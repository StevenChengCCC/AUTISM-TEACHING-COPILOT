#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/usability-study"
OUTPUT = ROOT / "output/pdf/round16g/teacher-evaluation-study-kit.pdf"
ORDER = [
    "FACILITATOR_GUIDE.md",
    "PARTICIPANT_INFORMATION_CONSENT_DRAFT.md",
    "PROTOCOL.md",
    "SYNTHETIC_CASE_ASSIGNMENTS.md",
    "TASK_SCRIPT.md",
    "OBSERVATION_AND_TIMING_SHEET.md",
    "POST_TASK_QUESTIONNAIRE.md",
    "PRINT_INSPECTION_CHECKLIST.md",
    "ISSUE_SEVERITY_RUBRIC.md",
    "ANALYSIS_TEMPLATE.md",
    "RELEASE_DECISION_WORKSHEET.md",
    "PARTICIPANT_DATA_DELETION_CHECKLIST.md",
]


def _clean(value: str) -> str:
    value = (
        value.replace("–", "-")
        .replace("—", "-")
        .replace("≤", "&lt;=")
        .replace("≥", "&gt;=")
    )
    value = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    return value


def _page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawString(
        0.65 * inch,
        0.42 * inch,
        "Autism Teaching Copilot - synthetic teacher evaluation kit v1",
    )
    canvas.drawRightString(7.85 * inch, 0.42 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _table(lines: list[str], width: float, styles) -> Table:
    rows = [
        [
            Paragraph(_clean(cell.strip()), styles["TableCell"])
            for cell in line.strip().strip("|").split("|")
        ]
        for line in lines
    ]
    if len(rows) > 1 and all(
        set(cell.text if hasattr(cell, "text") else "") <= {"-", ":"}
        for cell in rows[1]
    ):
        rows.pop(1)
    count = max(len(row) for row in rows)
    for row in rows:
        row.extend([Paragraph("", styles["TableCell"])] * (count - len(row)))
    table = Table(rows, colWidths=[width / count] * count, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sample = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle(
            "Title",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=27,
            textColor=colors.HexColor("#173B57"),
            spaceAfter=14,
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=sample["Heading1"],
            fontSize=19,
            leading=23,
            textColor=colors.HexColor("#173B57"),
            spaceBefore=8,
            spaceAfter=10,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=sample["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1D4E89"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=sample["BodyText"],
            fontSize=10.5,
            leading=15,
            textColor=colors.HexColor("#172033"),
            spaceAfter=7,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=sample["BodyText"],
            fontSize=10.5,
            leading=15,
            leftIndent=16,
            firstLineIndent=-10,
            spaceAfter=5,
        ),
        "TableCell": ParagraphStyle(
            "TableCell", parent=sample["BodyText"], fontSize=7.5, leading=9.5
        ),
        "Cover": ParagraphStyle(
            "Cover",
            parent=sample["BodyText"],
            fontSize=12,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#334155"),
        ),
    }
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="Synthetic Teacher Evaluation Kit",
        author="Autism Teaching Copilot",
    )
    story = [
        Spacer(1, 1.15 * inch),
        Paragraph("Real-Teacher Evaluation Kit", styles["Title"]),
        Paragraph("teacher-usability-v1", styles["Cover"]),
        Spacer(1, 0.25 * inch),
        Paragraph(
            "A 60-minute, privacy-safe protocol for 3-5 special educators using synthetic cases only.",
            styles["Cover"],
        ),
        Spacer(1, 0.25 * inch),
        Paragraph(
            "Consent language is a draft for legal/privacy review and is not legal advice. Creating this kit is not evidence that a teacher study, security review, physical printer check, or staging smoke has occurred.",
            styles["Cover"],
        ),
        PageBreak(),
    ]
    for file_index, name in enumerate(ORDER):
        lines = (SOURCE / name).read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not line:
                index += 1
                continue
            if line.startswith("|"):
                block = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    block.append(lines[index].strip())
                    index += 1
                story.extend((_table(block, doc.width, styles), Spacer(1, 8)))
                continue
            if line.startswith("# "):
                story.append(Paragraph(_clean(line[2:]), styles["H1"]))
            elif line.startswith("## "):
                story.append(Paragraph(_clean(line[3:]), styles["H2"]))
            elif re.match(r"^[-*] ", line):
                story.append(Paragraph("&#8226; " + _clean(line[2:]), styles["Bullet"]))
            elif re.match(r"^\d+\. ", line):
                story.append(Paragraph(_clean(line), styles["Bullet"]))
            else:
                story.append(Paragraph(_clean(line), styles["Body"]))
            index += 1
        if file_index < len(ORDER) - 1:
            story.append(PageBreak())
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    print(OUTPUT)


if __name__ == "__main__":
    main()
