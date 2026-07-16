# Round 7 — Amazon Cognito staging setup

This is the exact staging checklist for Lesson Kit Studio's browser-based teacher login. It creates public-client OIDC configuration; it does not create an enterprise tenant administrator.

## 1. Create the user pool

1. In the same AWS Region as the staging backend, create a Cognito User Pool named `lesson-kit-studio-staging`.
2. Choose email as the sign-in identifier. For a controlled demo, administrator-created accounts with email verification are recommended.
3. Keep self-registration disabled unless the demo explicitly needs it.
4. Require a strong temporary password and require the teacher to change it on first login.
5. For staging, optional MFA is acceptable; for production, require MFA after completing recovery and support procedures.
6. Use a short access/ID-token lifetime (recommended 60 minutes) and an appropriate refresh-token lifetime (recommended one day for a shared demo device, up to seven days for a controlled teacher device).

## 2. Define organization ownership

Create a mutable custom string attribute named `organization_id`. Assign the synthetic staging account a value such as `demo-organization`. The backend reads the signed ID-token claim `custom:organization_id`; it never accepts organization identity from a request body or custom browser header.

Create the optional group `lesson-kit-admins` only for demo administrators. Normal teachers do not need this group.

## 3. Create a public app client

Create an app client named `lesson-kit-studio-web`:

- Do **not** generate a client secret.
- Enable Authorization Code Grant only.
- Enable PKCE (`S256`) in the browser flow.
- Enable scopes `openid`, `email`, and `profile`.
- Do not enable implicit grant.
- Configure the Cognito managed login domain or a custom domain.

Configure exact URLs (replace the examples):

- Callback: `https://staging.example.amplifyapp.com`
- Sign-out: `https://staging.example.amplifyapp.com`
- Local callback/sign-out, only on a development app client: `http://localhost:5173`

Do not use wildcard callback or logout URLs.

## 4. Backend Elastic Beanstalk variables

Set these on the backend environment (or inject secrets through an approved deployment mechanism):

```text
APP_ENV=staging
AUTH_MODE=cognito
DEV_ALLOW_ANON_TEACHER=false
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_example
COGNITO_APP_CLIENT_ID=public_app_client_id
COGNITO_DOMAIN=https://your-domain.auth.us-east-1.amazoncognito.com
COGNITO_ORGANIZATION_CLAIM=custom:organization_id
COGNITO_DEFAULT_ORGANIZATION_ID=demo-organization
COGNITO_ADMIN_GROUP=lesson-kit-admins
```

The backend validates RS256 signatures from the pool JWKS, exact issuer, ID-token audience or access-token client ID, token use, and expiration. No Cognito app-client secret is used.

## 5. Amplify public variables

Set only the public values documented in `ROUND_7_AMPLIFY_DEPLOYMENT.md`. Never put OpenAI keys, database credentials, S3 credentials, or an app-client secret in Amplify.

## 6. Create a synthetic test teacher

Create `teacher-demo@example.test` or another controlled non-deliverable/synthetic address supported by your test process. Do not commit its password. Store the initial password in a secure team password manager, require reset on first sign-in, and delete or disable the user after the demo window.

## Verification

1. Sign in through Cognito managed login.
2. Confirm the browser request carries a bearer token and no client secret.
3. Confirm `GET /api/v2/auth/me` returns only the verified teacher/organization summary.
4. Confirm an expired token produces `401` with code `session_expired`.
5. Confirm a token from another app client or user pool is rejected.
6. Confirm an unauthenticated request to `/api/v2/learners` is rejected while `/health/live` remains public.

