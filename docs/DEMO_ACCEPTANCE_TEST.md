# Final synthetic demo acceptance test

This test is the completion gate for the demonstration, not a claim of legal
compliance, district-scale readiness, accessibility certification, or safe use
with real student data. Run only with synthetic records and an authorized
staging operator.

Use these result labels:

- **PASS** — executed against the stated environment with retained evidence;
- **FAIL** — executed and did not meet the expected result;
- **BLOCKED** — could not execute because a required environment/resource was
  unavailable;
- **NOT RUN** — not yet attempted.

## Evidence header

Record in a private test record:

```text
UTC start/end:
Git commit:
Backend application version:
Alembic revision:
Amplify build ID and HTTPS origin:
AWS account alias and Region (not account credentials):
Synthetic Cognito username:
Synthetic organization ID:
RDS instance identifier:
Private S3 bucket identifier:
Tester/reviewer:
```

Never record passwords, access/ID tokens, API keys, database URLs, signed URLs,
source document text, full prompts, or full model responses.

## Preconditions

- [ ] Release checklist is complete.
- [ ] `/health/live` and `/health/ready` return 200 over HTTPS.
- [ ] Staging uses Cognito, PostgreSQL, private S3, explicit CORS, external AI,
      fail-closed provider behavior, and explicit skill versions.
- [ ] RDS automated backups, encryption, deletion protection, and retention are
      verified.
- [ ] S3 Block Public Access, encryption, lifecycle, and versioning decision are
      verified.
- [ ] The test PDF/DOCX/TXT and account contain synthetic information only.

## End-to-end product path

For every step record **status, UTC time, request ID/resource ID, expected
result, actual result, and defect link**. Do not copy content into the record.

1. **Sign in.** Use authorization-code + PKCE with the synthetic Cognito
   teacher. Expected: authenticated product shell; logout available; no browser
   client secret.
2. **Create a synthetic learner.** Expected: learner persists with server-owned
   organization/user scope.
3. **Upload a synthetic text PDF.** Expected: private, random S3 key with no
   learner identifier; visible upload and parse states.
4. **Parse.** Expected: extracted text is persisted separately; original binary
   is not sent to the AI provider. An image-only control PDF must report
   needs-OCR/manual review rather than empty success.
5. **Correct extracted text.** Expected: teacher correction saves with version
   handling and remains after refresh.
6. **Extract and confirm learner profile.** Expected: signals are traceable,
   editable, and require teacher confirmation.
7. **Create a lesson plan.** Expected: teacher message produces dynamic
   questions; teacher choices update the draft.
8. **Generate lesson package.** Expected: real provider/skill generation
   metadata, deterministic safe teaching structure, and no `local_mock` success
   in staging.
9. **Review quality and safety.** Expected: instructional guidance is visible,
   blocked/provider failures are distinguishable, and no legal-compliance claim
   appears.
10. **Edit and approve.** Expected: edited package/material version persists;
    approval is explicit; unsaved changes are not silently lost.
11. **Record a teaching session.** Expected: observation supports accuracy,
    engagement, prompting, participation, generalization, regulation/recovery,
    and independence.
12. **View progress.** Expected: small/non-linear progress is represented and
    “plateau” is not treated as absence of progress.
13. **Configure handoff.** Select approved overview/strategies/goals, date range,
    sessions, approved packages/materials, and synthetic transition notes.
    Confirm authorized educational handoff intent.
14. **Generate export.** Expected: persisted job transitions pending/processing
    to completed; history survives refresh.
15. **Download and inspect.** Expected: short-lived private URL produces a ZIP
    with `handoff-summary.pdf`, `progress-data.csv`, `handoff-data.json`,
    `README.txt`, and only selected approved printable materials.
16. **Delete export.** Expected: object deletion is verified and minimized job
    history remains as designed.
17. **Refresh browser.** Expected: learner, record metadata/text correction,
    confirmed profile, package/material versions, session/progress, and export
    history remain.
18. **Restart backend.** Expected: readiness returns and all representative data
    remains in PostgreSQL/S3.
19. **Redeploy the same backend version.** Expected: readiness returns and the
    same data remains; no seed overwrite or memory fallback occurs.
20. **Permission checks.** Expected: signed-out access is 401; a different
    synthetic organization cannot read the resources.

## Inspect the handoff artifact

Download through the authorized UI. Use a private temporary workstation
directory and delete the artifact after inspection.

```bash
unzip -t teacher-handoff.zip
unzip -l teacher-handoff.zip
mkdir -p /tmp/lesson-kit-export-review
unzip teacher-handoff.zip -d /tmp/lesson-kit-export-review
jq '.exportSchemaVersion, .selectedSections, .provenance' \
  /tmp/lesson-kit-export-review/handoff-data.json
head -n 5 /tmp/lesson-kit-export-review/progress-data.csv
```

Verify:

- [ ] PDF opens, paginates, has page numbers, print-safe margins, learner
      display label, timestamp/version, confidentiality notice, and AI-assisted
      labels where applicable.
- [ ] CSV is UTF-8 and values beginning with `=`, `+`, `-`, or `@` cannot become
      spreadsheet formulas.
- [ ] JSON has the documented versioned schema, selected sections, date range,
      approved-only content, timestamp, and provenance.
- [ ] ZIP paths are relative/safe, unambiguous, and match its manifest.
- [ ] Original uploads, raw extracted text, unapproved drafts, AI conversations,
      prompts/provider responses, audit logs, deleted content, credentials, and
      unnecessary contact details are absent.

## Persistence and privacy checks

- [ ] Restart and same-version redeploy evidence shows identical synthetic
      resource IDs and versions.
- [ ] Anonymous GET to the S3 source object returns access denied.
- [ ] Anonymous GET to the export object returns access denied.
- [ ] Presigned download works before expiration and fails after expiration.
- [ ] Database unavailability makes readiness fail and never activates memory.
- [ ] AI provider failure is explicit and never becomes realistic mock success.
- [ ] Logs contain request IDs and safe categories but no learner text, token,
      secret, signed URL, prompt, response body, or database URL.

## Backup and restore acceptance

1. Verify automated backup retention, encryption, deletion protection, and
   latest restorable time.
2. Create and wait for a manual staging snapshot.
3. Follow `docs/BACKUP_AND_RESTORE.md` to restore into a temporary private RDS
   instance and temporary no-traffic backend environment.
4. Verify representative learner, lesson, session, progress, and export
   metadata using the same application version.
5. Verify S3 objects separately; do not infer binary recovery from RDS.
6. Destroy temporary restore resources after evidence review.

Never run this drill against, or restore over, the active staging database.

## Current repository verification record

Round 8 local regression results and cloud execution status must be updated at
the end of implementation:

| Check | Status | Current evidence/limitation |
| --- | --- | --- |
| Backend automated suite | PASS | `201 passed, 1 skipped` on 2026-07-16; the skipped test is the optional live PostgreSQL integration. |
| Frontend production build | PASS | TypeScript and Vite production build completed on 2026-07-16 (64 modules transformed). |
| Live PostgreSQL integration | BLOCKED | Optional test skipped because no disposable `TEST_DATABASE_URL` was supplied. |
| Cognito + Amplify E2E | BLOCKED | Requires configured staging AWS resources and test account. |
| Private S3 E2E | BLOCKED | Requires configured staging bucket and IAM role. |
| Elastic Beanstalk restart/redeploy | BLOCKED | Requires authorized staging deployment access. |
| RDS snapshot/restore drill | BLOCKED | Requires authorized staging RDS access and an approved drill window. |
| CloudWatch alarm delivery | BLOCKED | Requires staging log groups, metrics, SNS target, and test alarm. |

Code tests may support “ready with limitations”; they do not convert a blocked
AWS row to PASS. The project must not be described as operationally complete
until the cloud rows have actually passed.
