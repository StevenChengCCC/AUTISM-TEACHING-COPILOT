# Lesson Kit Studio 8–12 minute demo runbook

Use synthetic learner, teacher, record, lesson, and progress data only. This
script demonstrates a teacher-assistive workflow and its technical reliability;
it does not demonstrate diagnosis, treatment, legal compliance, accessibility
certification, or district-scale production readiness.

## Before the audience joins

- Complete `docs/RELEASE_CHECKLIST.md` and record the staging build IDs.
- Confirm live/readiness, Cognito login, PostgreSQL, private S3, external AI,
  explicit skill versions, and one recent backup.
- Use a synthetic text PDF small enough to parse quickly.
- Open the product signed out and keep CloudWatch/RDS consoles closed unless a
  technical question requires them; never show secrets, tokens, logs containing
  content, or signed URLs.
- Have a pre-created synthetic learner/package only as a recovery path. Clearly
  label it pre-created; never present local mock output as a successful live AI
  result.

## 0:00–1:00 — Teacher pain point

“Special-education teachers often prepare individualized, printable supports
across scattered records and tools. Lesson Kit Studio keeps the teacher as the
decision maker: AI proposes, the teacher reviews, edits, and approves.”

Sign in with the synthetic Cognito teacher. Point out the low-density workflow:
Learner → Records → Profile → Lesson → Outputs.

## 1:00–3:00 — Upload and profile extraction

Create a synthetic learner and upload the synthetic PDF.

While it processes, explain:

- the browser uploads directly with a short-lived presigned URL;
- the object is private, encrypted, and has a random server-controlled key;
- PostgreSQL stores metadata and extracted/corrected text, not the binary;
- scanned/image-only PDFs are marked for OCR/manual review rather than treated
  as empty success;
- malware scanning is not configured for this demo, so the product does not
  claim the file was scanned.

Review extracted text, correct one phrase, then review the proposed profile.
Edit one support need and confirm it. Emphasize source traceability and teacher
confirmation.

## 3:00–5:30 — Teacher-controlled lesson planning

Enter: “I want to teach asking for help during classroom routines.”

Show dynamic questions for response level, scenarios, materials, motivation,
and prompting. Change one option or add a teacher-authored option. Explain that
uploaded text remains untrusted task context and is not inserted into system
instructions.

Generate the package. Point out provider/model/skill version metadata, explicit
teacher-review requirement, and the fail-closed behavior: a provider failure is
shown as a retryable failure, not disguised as mock success.

## 5:30–7:30 — Classroom-ready review and control

Review the lesson brief, teaching flow, instructional quality/safety guidance,
and printable materials. Edit a sentence, save it, open the token board or help
card, and approve it for print.

Explain that checks are instructional guidance, not legal compliance. The
website remains the source of truth; external export is secondary.

## 7:30–9:00 — Session and progress

Record a short synthetic teaching session. Show that progress includes:

- engagement and participation;
- prompt fading;
- independence;
- generalization attempts;
- regulation/recovery;
- accuracy without making it the only measure.

Open the progress summary. “Small wins matter, and a plateau does not mean no
progress.”

## 9:00–10:30 — Authorized teacher handoff

Select approved overview, strategies/goals, date range, recent sessions,
approved packages/materials, and a short synthetic transition note. Review the
default exclusions, confirm authorized educational handoff intent, and generate
the export.

Download the private ZIP and briefly show its PDF, CSV, JSON, README, and
approved printable material. Explain CSV formula protection, approved-only
filtering, short-lived download, expiration/deletion, and persisted export
history.

## 10:30–12:00 — Technical reliability and boundaries

Refresh the browser and show the learner, corrected record, approved profile,
package, session/progress, and export history still present.

Conclude:

- PostgreSQL persists product state across restart/redeploy;
- private S3 stores source/export binaries separately;
- Cognito establishes teacher identity and organization scope;
- structured minimized logs, readiness checks, backups, and restore runbooks
  support repeatable staging demonstrations;
- cloud backup/restore and alarm status are only claimed when the recorded AWS
  acceptance checks have actually passed.

## Failure contingencies

- **AI unavailable:** show the clear provider-failure state, preserve the saved
  draft, and continue with an already approved synthetic package. State that it
  is pre-created.
- **Upload unavailable:** stop the upload portion and show a previously parsed
  synthetic record. Do not call a failed record ready.
- **Backend/database unavailable:** stop writes and show readiness status. Do
  not switch to memory/SQLite.
- **S3 unavailable:** preserve database state and show failed/retryable status.
  Never make the bucket public.
- **Login expired:** demonstrate the sign-in-again state; do not bypass auth.

After the demo, delete downloaded artifacts from the presenter device and clean
up synthetic records according to the demo retention plan.

