# Round 2: Amazon RDS PostgreSQL Setup

This guide prepares a synthetic-data staging environment. It is not approval to
store real student records.

## Target topology

- Elastic Beanstalk and RDS use the same VPC.
- RDS is deployed into private subnets and is not publicly accessible.
- The RDS security group accepts TCP 5432 only from the Elastic Beanstalk EC2
  instance security group.
- Storage encryption, automated backups (minimum seven days), and deletion
  protection are enabled.
- The demo may use a small single-AZ PostgreSQL instance. Production should use
  a decoupled RDS lifecycle, Multi-AZ as appropriate, private connectivity,
  tested restore procedures, and stricter operational controls.

AWS references: [RDS credentials in Secrets Manager](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/rds-external-credentials.html)
and [Elastic Beanstalk environment secrets](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.secrets.env-vars.html).

## Console procedure

1. Create a DB subnet group from at least two private subnets in the Elastic
   Beanstalk VPC.
2. Create an RDS PostgreSQL instance with public access disabled, encryption
   enabled, backup retention at least seven days, and deletion protection on.
3. Create a dedicated database and least-privilege application user. Do not use
   the RDS master user from the web application.
4. Create a security group rule with source equal to the Elastic Beanstalk EC2
   instance security group, protocol TCP, port 5432. Do not use `0.0.0.0/0`.
5. Store the complete SQLAlchemy URL as a single Secrets Manager secret value:

   `postgresql+psycopg2://USER:PASSWORD@PRIVATE_HOST:5432/DB_NAME`

6. On a supported Elastic Beanstalk platform, map that secret ARN to the
   `DATABASE_URL` environment secret. Give the EC2 instance profile only
   `secretsmanager:GetSecretValue` for that ARN and `kms:Decrypt` only when a
   customer-managed KMS key requires it.
7. Add the non-secret environment values below and deploy the application only
   after the migration procedure succeeds.

## Required Elastic Beanstalk values

```text
APP_ENV=staging
V2_REPOSITORY_MODE=sqlalchemy
V2_SEED_SYNTHETIC_DATA=false
DATABASE_URL=<Secrets Manager environment-secret reference>
ALLOWED_ORIGINS=https://<staging-frontend-domain>
DEV_ALLOW_ANON_TEACHER=false
AI_FAILURE_MODE=fail_closed
```

`V2_REPOSITORY_MODE` is forced to `sqlalchemy` in strict runtime modes even if a
bad value is supplied. A missing/unreachable PostgreSQL database makes
`/health/ready` fail; Backend v2 never falls back to memory in staging.

## CLI outline

Replace every placeholder before running. Do not paste passwords into shell
history; create the secret through an approved secure input mechanism.

```bash
aws rds create-db-instance \
  --db-instance-identifier <demo-db-id> \
  --engine postgres \
  --db-instance-class <small-demo-class> \
  --allocated-storage 20 \
  --storage-encrypted \
  --backup-retention-period 7 \
  --no-publicly-accessible \
  --deletion-protection \
  --db-subnet-group-name <private-db-subnet-group> \
  --vpc-security-group-ids <rds-security-group> \
  --master-username <bootstrap-admin>
```

Do not include `--master-user-password` in a committed script. Prefer RDS
managed master credentials or an interactive/secure deployment workflow.

Configure the application secret as an Elastic Beanstalk environment secret
using the `aws:elasticbeanstalk:application:environmentsecrets` namespace, then
set the non-secret values through normal environment properties. Secret values
are refreshed at instance bootstrap; after rotation, restart/update the
environment so all instances receive the new value.

## Network verification

From the migration runner or one controlled Elastic Beanstalk instance:

```bash
python -c "from app.core.database import check_database; assert check_database()"
```

Do not print `DATABASE_URL`, `RDS_PASSWORD`, or the resolved secret.
