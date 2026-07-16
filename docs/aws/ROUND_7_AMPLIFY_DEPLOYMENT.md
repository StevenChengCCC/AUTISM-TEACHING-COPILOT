# Round 7 — Amplify and Elastic Beanstalk deployment

The frontend is React 19 built by Vite. Its verified API-base variable is `VITE_API_BASE`. `amplify.yml` uses the `frontend` monorepo root and runs the deployment-variable safety check before `npm run build`.

## Required Amplify branch variables

For the staging branch configure:

```text
VITE_API_BASE=https://api-staging.example.com/api
VITE_USE_LOCAL_MOCK=false
VITE_AUTH_MODE=cognito
VITE_COGNITO_REGION=us-east-1
VITE_COGNITO_USER_POOL_ID=us-east-1_example
VITE_COGNITO_APP_CLIENT_ID=public_app_client_id
VITE_COGNITO_DOMAIN=https://your-domain.auth.us-east-1.amazoncognito.com
VITE_COGNITO_REDIRECT_URI=https://staging.example.amplifyapp.com
VITE_COGNITO_LOGOUT_URI=https://staging.example.amplifyapp.com
VITE_COGNITO_SCOPES=openid email profile
```

These values identify public endpoints and a public browser client. They are not secrets. Do not configure `OPENAI_API_KEY`, `DATABASE_URL`, `RDS_PASSWORD`, `AWS_SECRET_ACCESS_KEY`, Cognito app-client secrets, or other backend-only secrets in Amplify. The build validation deliberately fails a deployed branch when required public values are missing, HTTP is used, or known backend secrets are present.

## Elastic Beanstalk staging variables

In addition to the Cognito variables in `ROUND_7_COGNITO_SETUP.md`, configure:

- `APP_ENV=staging`
- `ALLOWED_ORIGINS=https://staging.example.amplifyapp.com`
- PostgreSQL/RDS variables from Round 2
- private S3 variables from Rounds 3 and 6
- non-mock AI provider and fail-closed configuration from Rounds 4–5
- `PUBLIC_API_BASE_URL=https://api-staging.example.com`

`ALLOWED_ORIGINS` must contain exact HTTPS Amplify/custom origins. Do not use `*`. Credentialed wildcard CORS is not configured. The load balancer health check should use `/health/live`; deployment acceptance should separately require `/health/ready` to return 200.

## Deploy order

1. Provision or verify RDS, private S3, Secrets Manager, Cognito, and backend IAM.
2. Run the one-time Alembic migration process documented in `docs/deployment/DATABASE_MIGRATIONS.md`.
3. Deploy Elastic Beanstalk and wait for `/health/ready`.
4. Add the final Amplify domain to Cognito callback/logout URLs and backend `ALLOWED_ORIGINS`.
5. Configure Amplify variables and deploy the staging branch.
6. Run the end-to-end demo script.

## Rollback

Frontend rollback: redeploy the preceding successful Amplify build. Backend rollback: deploy the preceding Elastic Beanstalk application version and follow the database rollback policy rather than automatically downgrading shared data. Cognito callback URLs and CORS should retain only active, authorized domains.

