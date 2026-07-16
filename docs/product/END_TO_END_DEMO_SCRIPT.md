# Lesson Kit Studio end-to-end staging demo

Use only synthetic/de-identified learner content. This script verifies the Round 7 experience; it is not a privacy, security, accessibility, or legal certification.

## Preconditions

- `/health/live` and `/health/ready` return 200.
- Amplify uses the staging HTTPS API and Cognito values.
- `VITE_USE_LOCAL_MOCK=false`.
- The synthetic teacher is assigned to `demo-organization`.
- Private S3 and PostgreSQL are configured.
- The external AI provider is configured fail-closed. A provider error must be visibly reported, never represented as a successful local mock.

## Demonstration

1. Open the Amplify URL and sign in with the synthetic Cognito teacher. Confirm logout is available in the account menu.
2. Select **Create New Learner** and use a synthetic learner code.
3. Upload synthetic TXT, text-PDF, or DOCX records. Observe upload and parsing progress. For an image-only PDF, demonstrate the needs-OCR/manual-review state rather than an empty successful extraction.
4. Review extracted text, correct a sentence, save, and confirm the learner profile. Reject or edit any unsupported profile signal.
5. In **Plan with AI Chat**, enter a goal, answer the generated questions, and confirm teacher-selected options.
6. Generate the lesson package. Review the explicit generation source, safety guidance, instructional quality checks, and blocked/provider-failure states where applicable.
7. Modify lesson content, observe the unsaved-change warning, save it, review a printable material, and approve it.
8. Create or resume a teaching session. Save a progress observation that includes engagement, prompting, participation, regulation/recovery, independence, and generalization—not accuracy alone.
9. Open Students and verify the slow/non-linear progress summary.
10. Generate a teacher handoff ZIP after selecting authorized sections and accepting the review confirmation. Download it through the short-lived private URL, then delete the export from history.
11. Refresh the browser. Verify the learner, records, corrected text, confirmed profile, saved package/materials, sessions/progress, and export history remain available from PostgreSQL/S3. The frontend restores the last safe workspace page using only resource IDs.
12. Sign out. Confirm protected endpoints no longer work. Sign in again and confirm saved data returns.

## Failure demonstrations

- Expire/revoke the session: the frontend returns to a clear sign-in-again screen.
- Use a teacher from another organization: resources must be absent or denied.
- Disable the AI provider: the UI shows a retryable provider failure and does not label mock output as successful AI content.
- Interrupt an upload: show retry/error state without creating a ready record.
- Stop the backend or database: readiness fails and the UI shows a recoverable API error.

## Acceptance record

Record the Amplify build ID, Elastic Beanstalk application version, migration revision, UTC test time, synthetic account identifier, and pass/fail notes. Never record passwords, tokens, source learner documents, complete prompts, or complete model responses.

