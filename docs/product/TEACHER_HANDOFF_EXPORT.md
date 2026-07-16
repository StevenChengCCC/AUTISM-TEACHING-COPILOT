# Teacher Handoff Export

Lesson Kit Studio creates a curated educational handoff, not a database dump. The website remains the source of truth. A teacher chooses the relevant approved sections, reviews the exclusions, adds transition notes, confirms the intended authorized handoff, and generates a private ZIP.

## Bundle

Every bundle contains:

- `handoff-summary.pdf` — print-ready Letter or A4 portrait summary with page numbers, safe margins, timestamp, export version, confidentiality notice, and AI-assisted-content notice.
- `progress-data.csv` — UTF-8 progress observations with spreadsheet formula protection.
- `handoff-data.json` — typed `teacher-handoff-v1` structured data.
- `README.txt` — file manifest, exclusions, handling notice, and schema version.
- `material-NN-TYPE.pdf` — optional, approved printable materials only.

The JSON schema contains the learner reference, selected sections, requested date range, approved profile content, active goals, progress, recent sessions, approved packages/materials, teacher transition notes, generation time, and minimized provenance.

## Approval and exclusions

The exporter includes a profile only after teacher confirmation and includes packages/materials only when their status is `approved`. The default exclusions are:

- original uploads and raw or corrected extracted record text;
- unapproved AI drafts and internal AI conversations;
- prompts, raw provider responses, and provider-generation metadata;
- audit logs, deleted content, credentials, and unnecessary contact details.

The confirmation text is: “I reviewed this export and confirm that it is intended for an authorized educational handoff.” It is a workflow confirmation, not a claim of legal compliance.

## API workflow

1. `POST /api/v2/learners/{learnerId}/handoff-exports` creates and executes a persisted job.
2. `GET /api/v2/handoff-exports?learnerId=...` returns scoped history.
3. `GET /api/v2/handoff-exports/{exportId}` returns current state and progress.
4. `POST /api/v2/handoff-exports/{exportId}/download` returns a short-lived private URL.
5. `POST /api/v2/handoff-exports/{exportId}/retry` retries a failed or expired request as a new job.
6. `DELETE /api/v2/handoff-exports/{exportId}` deletes the private artifact and marks its persisted metadata deleted.

States are `pending`, `processing`, `completed`, `failed`, `expired`, and `deleted`. Execution is synchronous for the demo but isolated behind `V2HandoffExportService._execute`, so a later SQS worker can consume the same request and job model.

## CSV columns

`sessionDate`, `goal`, `opportunities`, `accuracyPercent`, `independencePercent`, `promptLevel`, `signalsHighlighted`, and `teacherNotes`.

Values whose trimmed form begins with `=`, `+`, `-`, or `@` are prefixed with an apostrophe before CSV serialization. Consumers should still treat exported educational data as untrusted input.

## Current demo limitations

- Jobs execute in the web process; there is no distributed queue yet.
- PDF rendering supports approved embedded base64 images when available. Remote images are not fetched during export.
- Authentication remains subject to the repository’s documented deployment-mode constraints.
- Automatic jurisdiction-specific redaction and legal-retention policy are not claimed.

