# Production readiness gate

Run from the repository root:

```bash
cd backend
python scripts/run_synthetic_smoke.py
python scripts/production_readiness_gate.py --environment production
```

The first command executes the stable synthetic corpus and writes JSON and Markdown under `output/readiness/`. The second performs a read-only, fail-closed audit of the active process configuration and repository evidence.

Statuses are strict:

- `PASS`: the stated check actually ran or its local code/test evidence was inspected.
- `FAIL`: a required property is absent or unsafe.
- `BLOCKED`: the property requires an external target or human/executed evidence that was unavailable. BLOCKED is never PASS.
- `NOT_APPLICABLE`: the check genuinely does not apply; it is not a substitute for missing evidence.

The report never emits secret values. Configuration names do not prove deployed state. A passing local corpus can raise the product only to Demo ready.

## Authorized staging continuation

No staging target is committed to this repository. After an owner supplies an explicitly authorized non-production URL and synthetic-test identity, run only from a secured shell:

```bash
export ATC_STAGING_API_BASE='https://approved-staging-api.example'
export ATC_STAGING_WEB_BASE='https://approved-staging-web.example'
export ATC_STAGING_TOKEN_FILE='/secure/non-repository/path/staging-token.txt'
export ATC_STAGING_SYNTHETIC_PACKAGE_ID='approved-synthetic-package-id'
export ATC_STAGING_SYNTHETIC_SESSION_ID='approved-synthetic-session-id'
export ATC_STAGING_SYNTHETIC_CONTEXT_IDS_JSON='["approved-synthetic-context-id"]'
export RUN_AUTHORIZED_STAGING_SMOKE='true'
cd backend
python scripts/production_readiness_gate.py --environment staging
python -m pytest -q tests/test_v2_authorized_staging_smoke.py
```

The staging test module is intentionally skipped unless all three variables and the explicit flag are present. The target must contain synthetic data only. The run will create/reset synthetic fixture data and session records, so obtain explicit authorization before it is executed. Expected provider cost must be confirmed as zero (fake provider) or approved in advance.
