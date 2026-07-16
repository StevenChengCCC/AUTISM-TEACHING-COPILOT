# Instructional AI Evaluation Process

The synthetic Round 5 regression set is at `backend/evaluation/round5_cases.json`. It covers complete, sparse, and contradictory records; missing interests; AAC; an older learner; a vague goal; unsafe content; prompt injection; malformed provider output; invented detail; mismatched data; and age-inappropriate material.

Run the offline deterministic gate from the repository root:

```bash
PYTHONPATH=backend python -m app.evaluation.round5_runner \
  --dataset backend/evaluation/round5_cases.json
```

The command does not instantiate or call OpenAI and reports `providerCalled: false`. A failed case exits non-zero. It is suitable for CI and requires no API key.

Provider-backed evaluation is intentionally separate and can only be requested with the explicit `--provider-backed` flag and non-mock configuration. It is not part of the deterministic completion gate and is never invoked accidentally.

The end-to-end tests in `backend/tests/test_v2_instructional_intelligence.py` additionally cover evidence review, privacy minimization, dynamic questions, schema validity, generation metadata, safety blocking, teacher edits, approval history, comparison, and restore.

