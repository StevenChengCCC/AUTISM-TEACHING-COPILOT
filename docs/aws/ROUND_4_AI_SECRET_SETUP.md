# Round 4 AWS AI secret setup

This round requires no OpenAI key in source control, the frontend, Amplify, Docker images, or deployment archives.

## Recommended staging setup

1. In AWS Secrets Manager, create a staging secret containing only the OpenAI API key. Use a distinct production secret later.
2. Grant the Elastic Beanstalk EC2 instance role `secretsmanager:GetSecretValue` only for that secret ARN and the KMS decrypt permission only when a customer-managed key requires it.
3. Inject the resolved secret into the backend process as `OPENAI_API_KEY` through a controlled deployment/startup mechanism. Do not print the resolved environment.
4. Configure these non-secret Elastic Beanstalk variables:

```dotenv
APP_ENV=staging
AI_PROVIDER=openai
AI_FAILURE_MODE=fail_closed
OPENAI_TEXT_MODEL=gpt-5.5
OPENAI_PACKAGE_MODEL=gpt-4.1-mini
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_PACKAGE_TIMEOUT_SECONDS=45
ACTIVE_LEARNER_PROFILE_SKILL_VERSION=v1
ACTIVE_LESSON_PLANNING_SKILL_VERSION=v1
ACTIVE_LESSON_GENERATION_SKILL_VERSION=v1
ACTIVE_MATERIAL_GENERATION_SKILL_VERSION=v1
ACTIVE_IMAGE_GENERATION_SKILL_VERSION=v1
```

5. Do not set `SKILL_ROOT` unless skills are deployed outside the default package path.
6. Deploy, then verify `/health/ready` reports `skillRegistry` and `aiFailurePolicy` ready. The existing development AI status endpoint is not public in staging.

## Amplify

Amplify receives only the frontend API base URL (`VITE_API_BASE`). Never configure `OPENAI_API_KEY` or image/search provider secrets in Amplify environment variables.

## Rotation and rollback

Rotate the secret in Secrets Manager, restart the backend environment, and verify a synthetic generation request. If the provider is unavailable, staging returns a retryable sanitized error; it never substitutes a realistic mock. Roll back skill behavior by restoring the previous explicit active-version variables, not by editing deployed skill files.
