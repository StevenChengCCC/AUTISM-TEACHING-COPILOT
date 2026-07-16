# Versioned AI skill architecture

Backend v2 loads instructional behavior from immutable, explicitly selected skill versions under `backend/app/skills`. Python services keep orchestration, validation, safety checks, and persistence; skill files contain model-facing role, task, and preliminary quality guidance.

## Runtime components

- `models.py` defines frozen manifests, skill definitions, prompt envelopes, and generation metadata.
- `loader.py` validates one exact `skillId:version` path. It never scans for the newest directory.
- `registry.py` maps configured skill IDs to explicit versions and caches successfully validated definitions.
- `prompt_builder.py` assembles a trusted system message and a separate untrusted data message.
- AI providers obtain skills through dependency-injectable registries. The OpenAI provider has no embedded instructional system prompts.

The active v1 skills are learner profile extraction, lesson planning, lesson generation, printable material generation, and image generation. Their `sourceReviewStatus` is `pending`: this infrastructure is functional, but Round 5 will complete instructional source review and content rules.

## Failure behavior

Development and tests may use deterministic mock output. Responses identify it with `generationStatus=local_mock` and `outputSource=local_mock` or `mock_fallback`.

Staging and production always fail closed. Provider request failures use `provider_failure`; model contract failures use `invalid_output`. A safe request ID accompanies API errors. No plausible mock lesson is silently substituted.

## Metadata

Generated product responses can include provider, model, skill ID/version, prompt/input/output/evaluator versions, timestamp, output source, status, and teacher-review requirement. Package and chat persistence retain this metadata in existing versioned payloads.
