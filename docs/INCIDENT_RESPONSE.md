# Incident response and CloudWatch baseline

This is a concise synthetic-demo operations guide, not an enterprise incident-
response, security, privacy, or legal-compliance program. Never paste learner
content, signed URLs, tokens, prompts, model responses, database URLs, or
secrets into CloudWatch, chat, tickets, or screenshots.

## First actions for any incident

1. Name an incident owner and record UTC start time, environment, application
   version, and request IDs only.
2. Protect teacher-authored work. Avoid database rollback, S3 deletion, or an
   application downgrade until persistence and migration compatibility are
   understood.
3. Use `/health/live` to distinguish a running process from
   `/health/ready`, which checks deployable capabilities and database access.
4. Stop or fail closed only the affected writes where possible. Never switch a
   staging AI outage to realistic mock output.
5. Preserve minimized logs and AWS service events; do not export raw student
   records as incident evidence.
6. Communicate a user-safe status, expected next update, and whether retrying is
   safe. Do not expose provider exception text.
7. After recovery, verify representative synthetic data and record the result.

## CloudWatch configuration

### Log collection and retention

Enable Elastic Beanstalk log streaming to CloudWatch Logs for application and
platform logs. The exact log-group names vary by platform and environment;
verify them in **Elastic Beanstalk > Environment > Configuration > Monitoring**
before creating filters. The backend emits minimized JSON containing event,
request ID, route, status, duration, and safe error categories.

Use a deliberate retention period (30 days is a reasonable synthetic-demo
default) rather than `Never expire`:

```bash
aws logs put-retention-policy \
  --log-group-name <elastic-beanstalk-application-log-group> \
  --retention-in-days 30
```

Do not enable SQL statement logging, request/response body logging, OpenAI SDK
debug bodies, boto3 wire logging, or authorization-header logging.

### Application metric filters

Create filters on the backend JSON log group. Examples use the event names
emitted by this repository:

| Signal | Filter pattern | Suggested demo alarm |
| --- | --- | --- |
| Readiness failure | `{ $.event = "http_request" && $.path = "/health/ready" && $.status_code = 503 }` | 2 in 5 minutes |
| Application 5xx | `{ $.event = "http_request" && $.status_code >= 500 }` | 5 in 5 minutes |
| Export failure | `{ $.event = "export_failure" && $.error_code = "EXPORT_GENERATION_FAILED" }` | 2 in 15 minutes |
| AI provider failure | `{ $.event = "provider_failure" && $.error_code = "provider_failure" }` | 3 in 10 minutes |
| Record parsing failure | `{ $.event = "record_parsing_failure" }` | 3 in 15 minutes |
| Unhandled backend error | `{ $.event = "unhandled_request_error" }` | 1 in 5 minutes |

Example metric creation (repeat with distinct names/patterns):

```bash
aws logs put-metric-filter \
  --log-group-name <backend-log-group> \
  --filter-name LessonKitExportFailure \
  --filter-pattern '{ $.event = "export_failure" && $.error_code = "EXPORT_GENERATION_FAILED" }' \
  --metric-transformations \
    metricName=ExportFailureCount,metricNamespace=LessonKitStudio/Staging,metricValue=1,defaultValue=0
```

Route alarms to an SNS topic owned by the demo operator. Test notifications
with a synthetic failure and record only the CloudWatch alarm/metric IDs.

### Native AWS alarms

Configure these with thresholds appropriate to the selected instance sizes:

- RDS `CPUUtilization` sustained above 80%;
- RDS `FreeStorageSpace` below the documented reserve;
- RDS `FreeableMemory` below the documented reserve;
- RDS `DatabaseConnections` near the instance's safe limit;
- RDS `DiskQueueDepth` or storage latency showing sustained pressure;
- Application Load Balancer `HTTPCode_Target_5XX_Count` and unhealthy hosts;
- Elastic Beanstalk enhanced-health degradation.

Alarms are not deployed by this repository. Until their names, actions, and a
test notification are recorded from the staging account, observability is
**ready with limitations**.

## AI provider outage

**Detect:** `provider_failure` alarms, retryable AI errors, provider dashboard,
and a sanitized development/protected staging provider status. Never expose or
test a secret from the browser.

**Contain:** keep `AI_FAILURE_MODE=fail_closed`. Do not set `AI_PROVIDER=mock`
in staging. If generation must be disabled, remove provider access or deploy a
configuration that leaves generation fail-closed while retaining learner,
profile, lesson-draft, session, progress, and export read access. Tell teachers
that generation is temporarily unavailable and that saved work remains.

**Recover:** confirm provider status and quota, rotate/configure the backend
secret if necessary, restart or refresh Elastic Beanstalk secret injection,
then run one synthetic generation. Verify generation metadata names the real
provider/skill version and does not say `local_mock`.

**Close:** verify teacher-authored drafts were unchanged and watch failure
metrics for 30 minutes. A dedicated generation feature switch is deferred; the
current demo uses fail-closed provider behavior.

## Database outage

**Detect:** `/health/ready` returns 503 with a sanitized database unavailable
check, RDS alarms fire, or application 5xx rises.

**Contain:** stop demonstrations and writes. Do not enable SQLite or memory
fallback. Keep `/health/live` for process diagnostics, communicate maintenance,
and avoid migrations or redeploy loops.

**Recover:** inspect RDS events, instance state, connections, storage, security
groups, Secrets Manager injection, and recent changes. Restore only into an
isolated temporary instance using `docs/BACKUP_AND_RESTORE.md`; never overwrite
active staging. If the active instance recovers safely, verify readiness before
traffic.

**Verify:** check a representative synthetic learner, package, session,
progress observation, and export job; confirm organization scoping and current
Alembic revision. Do not print database contents into logs.

## S3 outage or permissions failure

**Detect:** upload/export failures, S3 `AccessDenied`, parsing failure events,
or presigned upload/download failures.

**Contain:** preserve PostgreSQL rows and state. Mark the upload/export failed,
retain its retryable status, and do not claim a file is uploaded, scanned,
parsed, exported, or deleted when the S3 operation did not complete. Do not
make the bucket public as a workaround.

**Recover:** verify bucket Region, Block Public Access, ownership, encryption,
prefix-scoped instance-role policy, bucket policy, KMS permissions if used, and
object ownership. Create a new upload intent after an upload-processing failure;
use the persisted export retry action for a failed export.

**Verify:** upload a synthetic file, inspect its random server-controlled key,
parse it, generate/download/delete a synthetic export, and confirm anonymous
object URLs return access denied.

## Suspected OpenAI API-key exposure

1. Disable/revoke the suspected key in the provider console immediately.
2. Create a replacement secret through the approved secret workflow; never put
   it in source, Amplify, commands, tickets, or screenshots.
3. Update the Secrets Manager value referenced by Elastic Beanstalk.
4. Restart/update all backend instances so they receive the replacement.
5. Inspect provider usage, CloudTrail/Secrets Manager access, deployment logs,
   and repository history for scope; do not print secret values.
6. Verify the old key is invalid and one synthetic backend-only generation
   succeeds with the replacement.
7. If any real data may have been involved, stop and invoke the organization's
   formal privacy/security process; this demo runbook is insufficient.

## Suspected teacher-account compromise

1. Disable the Cognito user (`AdminDisableUser`).
2. Revoke sessions where supported (`AdminUserGlobalSignOut`) and expire any
   application session state.
3. Review minimized Cognito, application request-ID, and audit-event metadata.
   Do not assemble a new raw learner-data log.
4. Reset access and verify group/organization claims before re-enabling the
   synthetic account.
5. Test that the disabled/old session receives 401 and another organization is
   denied the affected resources.

Example commands use identifiers only, never passwords or tokens:

```bash
aws cognito-idp admin-disable-user \
  --user-pool-id <user-pool-id> --username <synthetic-teacher-username>
aws cognito-idp admin-user-global-sign-out \
  --user-pool-id <user-pool-id> --username <synthetic-teacher-username>
```

## Accidental learner deletion

1. Stop related writes and record the UTC time, request ID, learner UUID, and
   environment. Do not re-create a learner with guessed data.
2. Determine whether application soft-delete metadata remains and whether S3
   versioning was enabled at deletion time.
3. Restore RDS only into a temporary environment and inspect the last known
   complete learner/profile/lesson/session/progress graph there.
4. Recover an S3 object version only through the versioned recovery procedure
   in `docs/BACKUP_AND_RESTORE.md`.
5. Compare metadata and objects in the isolated environment before any
   authorized reintroduction to staging.
6. If S3 was unversioned or the retention window expired, clearly identify the
   unrecoverable original binary. An RDS backup does not recover it.
7. Never silently recreate incomplete records or claim a full recovery when
   only profile/extracted metadata was recovered.

