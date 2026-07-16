# Database Migrations

Alembic is the only schema creation mechanism in staging and production. The
application calls `Base.metadata.create_all` only in development/test.

## Local verification

```bash
python -m pip install -r backend/requirements.txt
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini current
```

To test a disposable database without changing application configuration:

```bash
ALEMBIC_DATABASE_URL=postgresql+psycopg2://<user>:<password>@<host>:5432/<db> \
  alembic -c backend/alembic.ini upgrade head
```

The URL is read only by the migration process. Never echo it or commit it.

## Staging release sequence

1. Take/verify an RDS snapshot and confirm backup retention.
2. Deploy the candidate artifact to a no-traffic environment or keep the
   existing environment serving while a single controlled migration runner is
   used.
3. Run exactly one `alembic -c backend/alembic.ini upgrade head` against the
   staging RDS database. Do not put this command in `Procfile`, a per-instance
   deployment hook, or application startup.
4. Verify `alembic current` equals head.
5. Deploy/swap the application version.
6. Verify `/health/live`, `/health/ready`, `/api/v2/health`, and the persistence
   checklist.

For a one-instance demo Elastic Beanstalk environment, an explicit SSH command
is acceptable:

```bash
eb ssh <staging-environment>
cd /var/app/current
alembic -c alembic.ini upgrade head
```

Confirm the virtual environment exposes `alembic`; platform paths can differ.
For multiple instances, run migrations from a dedicated one-off runner with
private RDS network access rather than selecting an arbitrary web instance.

## Creating later revisions

```bash
alembic -c backend/alembic.ini revision --autogenerate -m "concise change"
```

Review generated SQL, upgrade, downgrade, indexes, foreign keys, and data
backfills before committing. Test on PostgreSQL; SQLite is not sufficient for
PostgreSQL-specific behavior.
