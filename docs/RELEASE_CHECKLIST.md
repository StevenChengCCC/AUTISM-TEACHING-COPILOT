# Staging release checklist

Use this checklist for every synthetic-data staging release. A checked code
item is not evidence that its AWS counterpart is configured. Attach private AWS
evidence by resource ID and UTC time without secrets or learner content.

## 1. Scope and rollback

- [ ] Release owner, reviewer, UTC window, Git commit, Elastic Beanstalk
      application version, Amplify build ID, and change summary are recorded.
- [ ] Only synthetic data will be used.
- [ ] Deferred work and known limitations were reviewed.
- [ ] Previous known-good backend application version and frontend build are
      available.
- [ ] Database downgrade compatibility was reviewed; rollback will not run a
      destructive downgrade merely to match old code.
- [ ] A manual RDS snapshot completed and its identifier was recorded.

## 2. Automated validation

From the repository root, using the release dependency set:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --disable-warnings
cd ../frontend
npm ci
npm run build
npm run validate:deployment
```

- [ ] Backend tests pass; any skips are explained.
- [ ] PostgreSQL integration tests ran against a disposable PostgreSQL database,
      not only SQLite.
- [ ] Frontend build and deployment validation pass.
- [ ] No `.env.local`, token, database URL, signed URL, key, test password,
      generated learner record, export ZIP, or local database is in the release
      artifact.

## 3. Database and migrations

- [ ] RDS is private, encrypted, deletion-protected, and has at least 7 days of
      automated backup retention.
- [ ] Secrets Manager supplies the database connection to the backend only.
- [ ] The current Alembic revision and target head are recorded.
- [ ] Exactly one controlled migration runner executes:

  ```bash
  alembic -c backend/alembic.ini upgrade head
  alembic -c backend/alembic.ini current
  ```

- [ ] Migrations do not run from every web instance or application startup.
- [ ] `/health/ready` reports the database query successful after deployment.

## 4. Authentication, secrets, and CORS

- [ ] `APP_ENV=staging`, `AUTH_MODE=cognito`, and anonymous teacher mode is
      disabled.
- [ ] Cognito issuer, Region, user pool, public app-client ID, organization
      claim, and domain match this environment.
- [ ] Amplify callback and logout URLs exactly match the deployed HTTPS origin.
- [ ] Authorization-code flow with PKCE is enabled; no app-client secret is in
      the browser.
- [ ] `ALLOWED_ORIGINS` contains only the exact HTTPS Amplify/custom staging
      origins; no wildcard or unrelated localhost origin is present.
- [ ] OpenAI and database secrets are backend-only Secrets Manager values.
- [ ] Amplify variables contain no API key, database password, AWS secret key,
      or backend signing secret.
- [ ] A disabled/expired synthetic Cognito session receives a safe 401.

## 5. S3 privacy and retention

- [ ] Block Public Access is fully enabled.
- [ ] Object ownership is bucket-owner-enforced and server-side encryption is
      enabled.
- [ ] Instance-role access is limited to learner-record and export prefixes.
- [ ] Presigned URL lifetimes match configuration and no signed URL is logged.
- [ ] Amplify origin is the only required browser PUT CORS origin.
- [ ] Learner-record keys and export keys contain no name, learner code, email,
      or record title.
- [ ] Abandoned-upload and export-expiration lifecycle rules are scoped and
      verified.
- [ ] Versioning status and noncurrent-version retention are recorded.
- [ ] An anonymous GET to representative source/export objects returns access
      denied.

## 6. AI and instructional skills

- [ ] `AI_PROVIDER` names the intended external provider and
      `AI_FAILURE_MODE=fail_closed`.
- [ ] The backend-only provider status reports a configured provider without
      revealing a key.
- [ ] Active skill IDs and explicit versions are recorded.
- [ ] One synthetic lesson generation records provider/model/skill metadata.
- [ ] Provider failure produces a visible retryable failure, not a realistic
      successful mock result.
- [ ] Safety/quality checks and teacher-review requirements remain visible.

## 7. Upload, export, and product smoke test

- [ ] Sign in as a synthetic teacher and create a synthetic learner.
- [ ] Upload and parse synthetic TXT, DOCX, and text PDF records.
- [ ] Image-only PDF reports needs-OCR/manual review; the demo does not claim an
      antivirus scan if none is configured.
- [ ] Correct extracted text and confirm the profile.
- [ ] Plan/generate/edit/approve a lesson package and printable material.
- [ ] Record a session with engagement, prompting, participation,
      generalization, regulation/recovery, and independence signals.
- [ ] Generate the authorized teacher handoff export.
- [ ] Inspect PDF, CSV, JSON, ZIP manifest, approved-only filtering, and default
      exclusions.
- [ ] Export download is private, short-lived, auditable, and deletable.
- [ ] Browser refresh and backend restart preserve the workflow state.

## 8. Observability and backup

- [ ] Elastic Beanstalk application logs stream to CloudWatch with an explicit
      retention period.
- [ ] Application 5xx, readiness, export, AI provider, and record parsing metric
      filters exist and test notifications reached the operator.
- [ ] RDS health/storage/connection alarms and ALB unhealthy/5xx alarms are
      active.
- [ ] Logs were sampled and contain no student text, token, prompt, signed URL,
      provider body, database URL, or secret.
- [ ] The backup verification checklist was completed.
- [ ] The most recent isolated restore drill date and result are recorded.

## 9. Deploy and verify

- [ ] Deploy backend application version; do not mutate active RDS from instance
      startup hooks.
- [ ] Verify `GET /health/live`, `GET /health/ready`, and
      `GET /api/v2/health` over HTTPS.
- [ ] Deploy the Amplify branch with its environment-specific public values.
- [ ] Run the concise demo path and one permission-denial check.
- [ ] Monitor 5xx, readiness, RDS, and application logs for at least 15 minutes.
- [ ] Record go/no-go decision and reviewer.

## Rollback

If the application is unhealthy but the schema remains backward-compatible,
deploy/swap to the previous backend version and roll Amplify back to its
previous build. If schema compatibility is uncertain, stop writes and follow
the database restore/migration runbooks; do not run a destructive downgrade
against active staging without a reviewed data plan. Preserve private S3
objects and export metadata until their normal retention/deletion policy is
understood.

Release is **no-go** if readiness fails, PostgreSQL/S3 falls back to local or
memory storage, authentication is anonymous, CORS is wildcard, AI failure is
presented as mock success, source/export objects are public, migration evidence
is missing, or backup status is unknown.

