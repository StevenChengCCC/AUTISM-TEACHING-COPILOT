# Round 6 — Private Export Storage on AWS

## Decision

The demo uses a dedicated private prefix, `teacher-handoff-exports/`, in the same private S3 bucket used by learner-record uploads. This reduces demo infrastructure while preserving IAM and lifecycle separation. A separate export bucket can be introduced later without changing the `PrivateObjectStorage` interface.

Never use a public bucket or `public-read` ACL. The application writes random keys such as `teacher-handoff-exports/ab/<uuid>.zip`; learner names, codes, record titles, and emails are forbidden in keys.

## Elastic Beanstalk configuration

Set backend-only environment values:

```text
OBJECT_STORAGE_PROVIDER=s3
S3_BUCKET=<private-bucket-name>
S3_REGION=<region>
S3_EXPORT_PREFIX=teacher-handoff-exports
S3_SERVER_SIDE_ENCRYPTION=AES256
EXPORT_DOWNLOAD_TTL_SECONDS=300
EXPORT_RETENTION_DAYS=7
MAX_EXPORT_BYTES=52428800
```

SSE-S3 (`AES256`) is acceptable for this synthetic demo. Use `aws:kms` plus `S3_KMS_KEY_ID` where organizational policy requires a customer-managed key. Do not put AWS credentials in source, frontend environment variables, or Elastic Beanstalk application code; use an instance profile.

## Least-privilege IAM

The Elastic Beanstalk instance role needs only:

- `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, and `s3:HeadObject` on `<bucket>/teacher-handoff-exports/*`;
- the corresponding learner-record prefix permissions required by Round 3;
- KMS encrypt/decrypt/data-key permissions only when SSE-KMS is enabled.

It does not need `s3:PutObjectAcl`, public policy access, or unrestricted bucket access. Keep S3 Block Public Access enabled and Object Ownership set to bucket-owner-enforced.

## Lifecycle

Add a lifecycle rule scoped to `teacher-handoff-exports/`:

1. Expire current objects after the approved retention window (seven days for demo).
2. Abort incomplete multipart uploads after one day.
3. If versioning is enabled, expire noncurrent versions according to organizational policy.

The persisted ExportJob may be retained as minimized history after its object expires. Its status becomes `expired`; the application must not issue a URL.

## Presigned downloads

The backend issues presigned GET URLs only after scoped authorization and job-state checks. Default lifetime is five minutes. The response uses `Content-Disposition: attachment; filename="teacher-handoff.zip"`. Amplify never receives bucket credentials or provider keys.

## CloudWatch and auditing

Application logs should include request ID, export ID, state transition, duration, status, and minimized error type. Do not log learner content, selected notes, S3 signatures, object bytes, database URLs, or stack traces in user responses. Alarm on repeated `EXPORT_GENERATION_FAILED`, S3 access denied, and deletion failures.

## Staging verification

- [ ] S3 Block Public Access is on.
- [ ] An unauthenticated object URL returns access denied.
- [ ] EB role is limited to the private prefixes.
- [ ] Generated keys contain no learner identifier.
- [ ] Objects show the configured server-side encryption.
- [ ] Presigned GET works before TTL and fails after TTL.
- [ ] Lifecycle rule is scoped to the export prefix.
- [ ] DELETE removes the S3 object and keeps minimized job history.
- [ ] Export metadata survives backend restart/redeploy in PostgreSQL.
- [ ] CloudWatch logs contain no teacher notes, API keys, or signed URLs.

## Rollback

Disable new export creation at the application layer, leave existing completed jobs readable until their normal expiry, and deploy the prior application version. Do not delete the prefix until active jobs and retention requirements are reviewed. Database rollback is governed by the migration runbook; the Round 6 downgrade removes standalone export fields and therefore must first delete or archive standalone jobs.

