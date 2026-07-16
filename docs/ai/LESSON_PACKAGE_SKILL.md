# Lesson Package Skill

The `lesson_generation` and `material_generation` skills create a teacher-review draft only after lesson details are confirmed.

## Package contract

The package includes an overview, observable response, baseline, objective, success criterion, response modality, preparation checklist, five-part teaching flow, prompting/fading plan, engagement plan, neutral error correction, generalization and maintenance, aligned data specification, teacher adaptations, and editable post-session summary.

Each teaching step includes phase, duration, teacher action/script, expected learner response, wait time, prompt and reinforcement actions, error correction, data fields, transition cue, and a break option.

## Material contract

Typed specifications exist for visual card, choice board, first-then board, help card, break card, token board, sorting page, matching page, scenario cards, teacher cue card, data sheet, session summary, summary template, and handoff note. Specifications include purpose, audience, layout, margins, text limits, image need, contrast guidance, print checks, editable fields, and alt text.

## Review lifecycle

Output states are `generated`, `validation_failed`, `safety_review_needed`, `teacher_review_needed`, `approved`, `rejected`, and `superseded` (with `ready` retained for earlier material compatibility). Teachers can edit, approve, reject, regenerate a section, compare versions, or restore a snapshot. Editing approved content creates a new `teacher_review_needed` version; the approved snapshot remains available.

