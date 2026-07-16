# Staging Persistence Verification Checklist

Use synthetic data only.

- [ ] RDS is private, encrypted, deletion-protected, and has at least seven days
      of automated backup retention.
- [ ] RDS port 5432 accepts traffic only from the migration runner and Elastic
      Beanstalk instance security group.
- [ ] `DATABASE_URL` comes from Secrets Manager and is absent from source,
      frontend variables, logs, health responses, and deployment archives.
- [ ] `APP_ENV=staging`, `V2_SEED_SYNTHETIC_DATA=false`, explicit HTTPS CORS, and
      anonymous teacher mode disabled.
- [ ] One controlled runner completed `alembic upgrade head`.
- [ ] `/health/live` returns 200.
- [ ] `/health/ready` reports a successful database query. Other later-round
      capability gaps may still keep overall staging readiness at 503.
- [ ] Create synthetic learner `Persistence Test Learner`.
- [ ] Save its profile and confirm a subsequent GET returns the same version.
- [ ] Create a lesson chat/draft and a lesson package with generated materials.
- [ ] Record a teaching session and a progress observation.
- [ ] Create export metadata; do not expect a real exported binary in Round 2.
- [ ] Restart the backend process and confirm learner, profile, package,
      materials, session, observation, and export metadata still exist.
- [ ] Redeploy the same application version and confirm the same records still
      exist.
- [ ] Submit an update with a stale `expectedVersion`; confirm HTTP 409 with
      error code `version_conflict`.
- [ ] Query from a different synthetic organization scope; confirm the first
      organization's rows are not returned.
- [ ] Run `TEST_DATABASE_URL=<staging-test-url> pytest -q
      backend/tests/test_v2_sqlalchemy_persistence.py` from an approved runner.
- [ ] Remove the synthetic records or retain them under an explicit demo-data
      policy.
