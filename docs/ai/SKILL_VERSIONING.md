# AI skill versioning

## Selecting versions

Each active version is explicit:

```dotenv
ACTIVE_LEARNER_PROFILE_SKILL_VERSION=v1
ACTIVE_LESSON_PLANNING_SKILL_VERSION=v1
ACTIVE_LESSON_GENERATION_SKILL_VERSION=v1
ACTIVE_MATERIAL_GENERATION_SKILL_VERSION=v1
ACTIVE_IMAGE_GENERATION_SKILL_VERSION=v1
```

The registry never selects a version through lexical sorting. An unsupported or missing configured version produces `skill_configuration_error`. `/health/ready` reports the skill registry unavailable in strict environments without exposing filesystem paths.

## Creating a new version

1. Copy the prior version to a new exact directory such as `lesson_planning/v2`.
2. Change the manifest `version` and every schema, prompt-template, and evaluator identifier that actually changed.
3. Keep the old version immutable.
4. Add loader, contract, safety, and evaluation tests.
5. Complete source and teacher review; update `sourceReviewStatus` honestly.
6. Deploy the files before changing the active-version environment variable.
7. Promote one environment at a time and retain the prior value for rollback.

Changing prose in a published prompt requires a new prompt-template version. Breaking input/output changes require new schema versions. Evaluation-rule changes require a new evaluator version.

## Rollback

Restore the previous `ACTIVE_*_SKILL_VERSION` values and restart the backend. Because generation metadata records the prior version, existing content remains auditable and is not rewritten.
