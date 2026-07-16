# RDS and Application Rollback

Database and application rollback are separate decisions. Never downgrade a
schema merely because an application deployment failed.

## Preferred rollback

1. Stop new traffic to the failed application version.
2. Re-deploy the last known compatible application version.
3. Leave a backward-compatible schema in place when possible.
4. Confirm readiness and run synthetic read/write checks.

## Schema downgrade

Use only after reviewing the revision's `downgrade()` and confirming it will not
destroy data required for recovery.

```bash
alembic -c backend/alembic.ini current
alembic -c backend/alembic.ini downgrade <previous-revision>
```

The Round 2 initial migration downgrades to `base` by dropping the created
tables. That is suitable only for a disposable empty test database, never for a
staging database containing data.

## Snapshot restore

For destructive or uncertain failures:

1. Prevent application writes.
2. Restore the verified pre-deployment snapshot to a new RDS instance.
3. Validate row counts and synthetic records against the restored instance.
4. Update the Secrets Manager connection URL to the restored endpoint.
5. Refresh/restart Elastic Beanstalk so every instance receives the rotated
   secret value.
6. Verify readiness and the persistence checklist before reopening traffic.

Keep the failed database isolated for investigation. Never log its credentials
or copy learner text into tickets/logs.
