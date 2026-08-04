# Learner profile corrective implementation

## Root cause and exact loss stages

The failed N-482 result was not a DOCX parsing failure. Reviewed text reached the
provider, but the active prompt explicitly requested a brief summary, only two or three
support needs, and no more than five insights. The provider contract accepted only the
flat `LearnerProfile` plus legacy `ProfileSignal` objects. Any richer model keys had no
typed destination and Pydantic's previous extra-field behavior could discard them. The
merge service then populated only flat fields backed by a small category map. SQL stored
that already-reduced learner JSON, the public DTO exposed no richer profile, and the
frontend mapped only eight flat controls. Its empty-string fallbacks rendered confirmed
record facts as “Needs confirmation” or “Confirm with teacher.”

| Boundary | Before | After |
|---|---|---|
| Reviewed text | Full effective text, sanitized and capped at 50,000 characters | Unchanged; N-482 is below the cap |
| Provider prompt | Brief summary and 2–3 supports | Exhaustive evidence-linked factors with explicit status and constraints |
| Raw/parsed output | Flat learner and legacy signals | Strict typed canonical `normalizedProfile`; empty factors are invalid |
| Normalization | Non-additive flat merge with a limited signal map | Stable factor merge, status indexes, safe filtering, derived legacy fields |
| Database | JSON could persist only fields present in the model | Canonical JSON persists in profile payload and version snapshots |
| API | Canonical data omitted | `normalizedProfile` is serialized on learner DTOs |
| Frontend | Eight flat fields and confirmation fallbacks | Structured sections, distinct statuses, evidence, implication, edit/confirm |

No raw record text or learner PII was added to logs. Provider failures log only safe
failure metadata and return a retryable error; reviewed text and the previous profile are
preserved.

## Schema

`CanonicalLearnerProfile` contains the application-owned `learnerId`, age, typed
`ProfileFactor[]`, calculated current/unconfirmed/historical/excluded ID indexes,
blocking issues, and a derived compact summary. A factor contains:

```json
{
  "id": "stable-factor-id",
  "category": "communication",
  "label": "human-readable label",
  "value": "normalized actionable information",
  "status": "confirmed_current",
  "confidence": 0.98,
  "sourceEvidence": "short excerpt",
  "sourceRecordId": "record-id",
  "instructionalImplication": "how instruction changes",
  "generationConstraints": ["machine_readable_constraint"],
  "teacherReviewed": false
}
```

The full category/status unions are defined in `backend/app/schemas/v2_dto.py` and
mirrored in `frontend/src/v2/types.ts`. Unknown keys are forbidden at the extraction
contract. Flat fields remain compatible but are derived from the canonical factors when
structured evidence exists. Historical interests never populate current interests;
not-approved/not-meaningful reinforcers never populate current reinforcement.

## N-482 before and after

Before, the normalized representation did not exist. The effective flat result was:

```json
{
  "age": 9,
  "communicationMode": "",
  "supportNeeds": [],
  "interests": [],
  "attentionProfile": "engages 6-8 minutes in low-distraction tasks",
  "notes": "Avoid crowded worksheets, complex visuals, sudden sounds, hand-over-hand prompts, and emotionally intense graphics; favors blue accents and literal images; use short activity blocks with visible endpoints."
}
```

The exact after JSON is checked in as
`backend/tests/fixtures/n482_normalized_expected.json`. It contains 51 factors: 44
`confirmed_current`, 3 `unconfirmed`, 1 `historical`, 2 `not_approved`, and 1
`not_meaningful`. All 44 current factors are indexed, and hand-over-hand prompting plus
the three status-excluded reinforcers are indexed as excluded generation inputs.

## Prompt revision

The v2 learner-profile skill now requires all actionable factors, evidence for each,
exact CURRENT/HISTORICAL/UNCONFIRMED/NOT APPROVED/NOT MEANINGFUL/OMITTED mappings,
first-class access constraints, negative generation constraints, no clinical inference,
and strict JSON matching the backend schema. The trusted application learner ID always
overrides source-document codes.

## Persistence and migration

No Alembic migration is required. `v2_learner_profiles.payload` and
`v2_learner_profile_versions.payload` are JSON columns and already preserve the new
typed object. A SQLAlchemy restart/version test verifies the round trip. The version
loader was corrected to strip its internal `_dtoType` marker before strict validation.

## Acceptance and test results

- N-482 raw parse, normalization, in-memory persistence, DTO/API JSON, and frontend
  mapping: passed.
- Required communication, wait time, token count, audio/hand-over-hand prohibitions,
  four-choice limit, current interests, historical dinosaurs, excluded food/tablet/video,
  and unresolved language/image questions: passed.
- De-identification and application-owned learner ID: passed.
- Single-factor edit preserving all unrelated factors: passed.
- Synthetic N-482 text through real DOCX generation/parser: passed.
- SQL restart and profile-version persistence: passed.
- Frontend mapping/status grouping tests and production build: passed.
- Focused backend suite: 61 passed, 1 skipped.
- Full backend suite: 251 passed, 1 skipped, 2 unrelated pre-existing failures. The
  failures assert old lesson-material mock wording and lesson-planning skill version v1;
  this round did not modify those behaviors.

Commands used:

```sh
python3 -m pip install -r backend/requirements.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q backend/tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q backend/tests/test_v2_structured_profile_pipeline.py backend/tests/test_v2_record_upload.py backend/tests/test_v2_openai_provider.py backend/tests/test_v2_product.py backend/tests/test_v2_sqlalchemy_persistence.py
cd frontend && npm test
cd frontend && npm run build
python3 -m compileall -q backend/app
```

External pytest plugin autoload is disabled because the workstation's globally installed
`byu_pytest_utils` plugin crashes during this repository's parameterized collection.

## Manual routes checked

Using an ephemeral in-memory TestClient process with synthetic data:

- `POST /api/v2/learners` → 201; source learner ID was replaced by application ID.
- `PATCH /api/v2/learners/{id}/profile-factors/{factorId}` → 200.
- `POST /api/v2/learners/{id}/profile/confirm` → 200.

## Remaining risks

- Extraction completeness still depends on the configured model following the strict
  schema; invalid output now fails visibly and is retryable rather than silently falling
  back.
- Input records above 50,000 sanitized characters are truncated by the existing upload
  security boundary; N-482 is not affected.
- Existing legacy profiles acquire a compatibility canonical profile from legacy signals,
  but cannot recover evidence that was already lost before this change without re-running
  extraction from reviewed records.
- The two unrelated full-suite failures should be resolved in the lesson-material/skill
  version workstream, not by changing this profile correction.
