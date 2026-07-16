# Backup, restore, and object recovery

This runbook is for the synthetic-data staging demonstration. It does not
authorize storing real student records and it is not a disaster-recovery or
legal-compliance certification. Never restore over the active staging
database. A restore drill always creates an isolated temporary RDS instance
and a temporary backend environment.

## Required RDS baseline

Verify these properties in **RDS > Databases > staging instance** before each
release and record screenshots or CLI output in the private release record:

- automated backups are enabled;
- backup retention is at least 7 days;
- storage encryption is enabled;
- deletion protection is enabled;
- the instance is not publicly accessible;
- the security group allows PostgreSQL only from the Elastic Beanstalk and
  controlled migration-runner security groups;
- the latest automated backup time and maintenance window are understood;
- the application connection is injected from Secrets Manager, never Amplify.

Read-only verification (replace placeholders; output contains infrastructure
metadata, so keep it with the private release record):

```bash
aws rds describe-db-instances \
  --db-instance-identifier <staging-db-id> \
  --query 'DBInstances[0].{Encrypted:StorageEncrypted,DeletionProtection:DeletionProtection,BackupRetentionDays:BackupRetentionPeriod,PubliclyAccessible:PubliclyAccessible,LatestRestorableTime:LatestRestorableTime,Engine:Engine,EngineVersion:EngineVersion}'
```

Point-in-time recovery requires automated backups, a non-zero retention
window, and a target time between the instance's earliest and latest restorable
times. RDS point-in-time recovery creates a new instance; it is not an in-place
rollback. RDS backups restore PostgreSQL data and export metadata only. They do
not restore learner-record or export binaries stored in S3.

## Manual snapshot procedure

Create a snapshot before a migration or high-risk staging release. Snapshot
creation is non-destructive, but it is an AWS state change and must be run by an
authorized operator.

```bash
aws rds create-db-snapshot \
  --db-instance-identifier <staging-db-id> \
  --db-snapshot-identifier <staging-db-id>-pre-release-<YYYYMMDDHHMM>

aws rds wait db-snapshot-completed \
  --db-snapshot-identifier <snapshot-id>

aws rds describe-db-snapshots \
  --db-snapshot-identifier <snapshot-id> \
  --query 'DBSnapshots[0].{Status:Status,Encrypted:Encrypted,Created:SnapshotCreateTime,EngineVersion:EngineVersion}'
```

Do not put database passwords or a connection URL in commands, shell history,
screenshots, tickets, or this repository.

## Safe staging restore drill

No destructive restore is performed by application code. Use one of these
methods to create a temporary database.

### Snapshot restore

```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier <temporary-restore-db-id> \
  --db-snapshot-identifier <snapshot-id> \
  --db-instance-class <small-demo-class> \
  --db-subnet-group-name <private-db-subnet-group> \
  --vpc-security-group-ids <temporary-restore-security-group> \
  --no-publicly-accessible
```

### Point-in-time restore

```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier <staging-db-id> \
  --target-db-instance-identifier <temporary-restore-db-id> \
  --restore-time <UTC-ISO-8601-time> \
  --db-instance-class <small-demo-class> \
  --db-subnet-group-name <private-db-subnet-group> \
  --vpc-security-group-ids <temporary-restore-security-group> \
  --no-publicly-accessible
```

Then:

1. Wait for the temporary instance to become `available`.
2. Confirm encryption and private networking. Never add a public ingress rule.
3. Create a temporary Secrets Manager secret for the restored connection. Do
   not reuse or overwrite the active staging secret.
4. Clone the Elastic Beanstalk configuration into an isolated, no-public-
   traffic restore environment using the same application version that created
   the snapshot. Point only this environment at the temporary secret.
5. Keep `APP_ENV=staging`, Cognito authentication, explicit CORS, private S3,
   and fail-closed AI settings. Do not enable synthetic seeding.
6. Check `GET /health/live`, `GET /health/ready`, and `GET /api/v2/health`.
7. With an authorized synthetic test account, verify a representative learner,
   approved profile, lesson package/version, generated material/version,
   session, progress observation, export job, and audit metadata.
8. Confirm organization scoping by checking that a different synthetic
   organization cannot access those resources.
9. Do not run a new Alembic migration until the same-version validation is
   complete. If testing a newer release, snapshot the temporary restore first,
   run the migration once, and verify again.
10. Record identifiers and pass/fail results only; do not copy record text,
    prompts, tokens, or database URLs into the drill report.
11. Delete the temporary Elastic Beanstalk environment, temporary secret, and
    temporary RDS instance after the validation owner approves the evidence.
    Never target the active staging identifiers.

If deleting the temporary DB, explicitly check its identifier twice. Whether a
final snapshot is retained is a deliberate drill-evidence decision, not an
automatic default.

## Backup verification checklist

- [ ] Automated backup retention is at least 7 days.
- [ ] Latest restorable time is current enough for the release.
- [ ] Storage encryption and deletion protection are enabled.
- [ ] The database is private and its security-group source is restricted.
- [ ] A manual pre-release snapshot reached `available`.
- [ ] Snapshot encryption and engine version were recorded.
- [ ] A restore was made into a temporary, isolated RDS instance.
- [ ] Temporary backend readiness passed without a memory fallback.
- [ ] Representative synthetic learner, lesson, session, progress, and export
      metadata were found.
- [ ] Organization-scoped access remained enforced.
- [ ] S3 objects were checked separately; RDS restore was not assumed to restore
      binaries.
- [ ] Temporary restore resources were removed after validation.
- [ ] Evidence contains no password, token, source record, or learner content.

Until this checklist has been executed in the actual AWS account, backup and
restore status is **incomplete**, even though the code and runbook are ready.

## S3 retention and recovery

The demo uses a private bucket with two server-controlled prefixes:

- `learner-records/` for source documents;
- `teacher-handoff-exports/` for generated handoff ZIPs.

Keep Block Public Access on, bucket-owner-enforced ownership, server-side
encryption, and least-privilege instance-role access. The export prefix expires
current objects after the configured 7-day demo window. Abandoned upload
cleanup must target only unconfirmed temporary uploads; it must not expire
active learner records. Incomplete multipart uploads, if introduced, should be
aborted after one day.

### Versioning decision

Enable S3 Versioning for the synthetic staging bucket before relying on object
recovery. This repository does not create or verify that AWS setting, so its
current deployed state is **unverified**. Versioning improves accidental-delete
recovery but does not replace a retention policy, database backup, or tested
restore procedure. Lifecycle rules must also expire noncurrent versions within
the approved retention window.

An authorized operator can enable it explicitly:

```bash
aws s3api put-bucket-versioning \
  --bucket <private-bucket> \
  --versioning-configuration Status=Enabled
```

Verify:

```bash
aws s3api get-bucket-versioning --bucket <private-bucket>
aws s3api get-public-access-block --bucket <private-bucket>
aws s3api get-bucket-encryption --bucket <private-bucket>
aws s3api get-bucket-lifecycle-configuration --bucket <private-bucket>
```

### Recover an accidentally deleted synthetic object when versioning is enabled

1. Stop writes affecting the record or export and preserve its database state.
2. Obtain the server-controlled object key from an authorized backend/admin
   path. Do not derive it from learner data.
3. List versions and delete markers:

   ```bash
   aws s3api list-object-versions \
     --bucket <private-bucket> \
     --prefix <exact-server-controlled-key>
   ```

4. Select the last known good version and copy it to a new current version:

   ```bash
   aws s3api copy-object \
     --bucket <private-bucket> \
     --key <exact-server-controlled-key> \
     --copy-source '<private-bucket>/<exact-server-controlled-key>?versionId=<good-version-id>' \
     --server-side-encryption AES256
   ```

5. Verify ownership, encryption, size, MIME expectations, and backend-scoped
   access. Re-run parsing only through the normal validated record flow.
6. Record a minimized recovery audit event and remove any temporary copies.

If versioning was not enabled when the object was deleted, S3 cannot recover
the binary through this procedure. An RDS restore may recover only metadata and
extracted text. Do not silently recreate an incomplete learner record or claim
the original file was recovered.
