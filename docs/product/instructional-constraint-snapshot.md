# Instructional constraint snapshot implementation

## Root cause

The canonical factor profile stopped data loss at extraction, but downstream planning
still received `build_ai_safe_profile()`—a partial, flat dictionary—and package
generation rebuilt another dictionary from the latest learner. Drafts and packages had
no profile revision, so an old draft could silently generate against changed learner
information. Historical, excluded, and unresolved factors also lacked a single typed
downstream contract.

## New downstream contract

`InstructionalConstraintSnapshot` is now the only learner-personalization payload used
by the active planning and package-generation path. It contains typed communication,
instruction, visual/sensory/motor access, engagement, transition/break, generalization,
safety, unresolved, and excluded sections plus `profileRevision`, `generatedAt`, and
the contributing factor IDs. It contains no raw text, evidence excerpt, filename,
source-document identifier, learner code, contact, provider, school, address, or
non-instructional medical data.

Only `confirmed_current`, `teacher_confirmed`, `teacher_edited`, and explicitly derived
factors are active. A derived factor requires a
`derived_from_confirmed_factor=<factor-id>` constraint. Historical, unconfirmed,
not-approved, not-meaningful, rejected, and omitted factors cannot become active.
Historical interests, excluded items, and unresolved assumptions remain visible in
their dedicated snapshot arrays.

## Revision and invalidation

The revision is a versioned SHA-256 content fingerprint over normalized factor content,
instructionally relevant age, and reviewed/ready record IDs, versions, and effective-text
hashes. Raw text is not retained in the revision or sent to a provider. The revision
changes when reviewed record state/text or factor state/value changes.

Lesson drafts persist the revision and complete snapshot. Chat retrieval and answer
updates compare the draft revision with the latest profile; stale drafts return
`profileStale=true`, disable generation, and show a restart notice. Package generation
performs the same check server-side and returns a conflict for stale drafts. A package
stores the exact draft snapshot and revision. Later profile changes do not mutate an
approved historical package.

Older drafts without revision metadata remain compatible: the server attaches the
latest snapshot immediately before generation. A draft with an explicit old revision is
never silently upgraded.

## N-482 before and after

Before, downstream context contained selected flat keys such as communication mode,
interests, reinforcement preferences, supports, strengths, sensory preferences,
challenges, prompting preferences, and goals. It omitted explicit exclusion and status
boundaries, processing time, choice limit, visual/audio prohibitions, motor alternatives,
break/transition requirements, and a revision.

After, N-482 serializes speech and AAC acceptance, five-second processing time, six-minute
activity duration, visible endpoint, four-choice maximum, low-clutter/blue/literal visual
requirements, audio and angry-face exclusions, motor alternatives, current transit
interests, transit reinforcement and five-token requirement, specific praise,
First–Then/warning/two-minute break supports, prompt hierarchy, prohibited hand-over-hand
prompting, neutral correction, and three generalization contexts. Dinosaurs occur only
in historical interests; food and tablet/video occur only in not-approved/excluded
arrays; generic stars occur only as not meaningful; the three unresolved preferences
remain unresolved.

## Persistence and compatibility

No Alembic migration is required. Drafts, chats, learner profiles, packages, and package
versions already persist typed DTO payloads in JSON. Existing approved package payloads
deserialize with empty/default revision fields and remain viewable. Synthetic demo
learners were given explicit canonical factors so the existing vehicle/music/emotion
demo personalization remains intact without a flat-profile fallback.

## Verification

Commands:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q backend/tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q backend/tests -k 'not test_missing_interest_uses_neutral_context_and_profile_aware_mock_content and not test_mock_generation_records_versioned_metadata'
cd frontend && npm test
cd frontend && npm run build
python3 -m compileall -q backend/app
```

Results:

- New N-482 snapshot, provider payload, privacy, revision, stale-draft, API
  serialization, and approved-package immutability tests: passed.
- Backend suite excluding two documented pre-existing unrelated failures: 255 passed,
  1 skipped, 2 deselected.
- Full backend suite: 255 passed, 1 skipped, 2 pre-existing failures.
- Frontend tests: 2 passed.
- Frontend production build and Python compilation: passed.

The two existing failures are the neutral image-prompt wording assertion and a v1 skill
metadata assertion while the active configuration selects lesson-planning v2. Material
rendering and the three-question planning UX were not changed in this round.

## Remaining risks

- Provider quality still depends on factors containing useful machine-readable
  constraints; unsupported derived factors now fail closed from the active snapshot.
- Record text beyond the existing 50,000-character sanitized boundary remains truncated
  before extraction.
- Legacy persisted profiles that never had canonical factors need re-extraction or a
  deliberate migration; downstream code will not infer active constraints from their
  old flat summaries.
