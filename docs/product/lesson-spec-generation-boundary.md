# LessonSpec generation boundary

`LessonSpec` is the canonical, versioned input for lesson-package and material-content generation.
The public package endpoint may continue receiving a legacy `LessonDesignDraftDto`, but
`V2LessonSpecService` immediately adapts it, records compatibility/default provenance,
validates it against the current `InstructionalConstraintSnapshot`, and stops generation
when validation fails. Providers and downstream material builders receive `LessonSpec`,
not the legacy draft or a free-form learner-context dictionary.

## Deterministic application ownership

Application code owns:

- IDs, schema version, revision, learner/profile revision, and decision IDs;
- teacher-authored and teacher-selected values;
- accepted response modes, processing time, prohibited prompts, activity limits,
  safety exclusions, access requirements, selected contexts, and profile-factor lineage;
- token count/theme, selected reward, break timing, transition rules, and excluded reinforcers;
- selected material coverage, library provenance/configuration, and unsupported status;
- goal-specific data measures, trial/independence definitions, validation, package status,
  approval state, and stale-output invalidation;
- field-level source, reason, and teacher-confirmation requirements for derived/default values.

AI output is treated as a proposal and cannot replace those fields. After provider output,
the package service reapplies LessonSpec semantics to token boards, data sheets, scenario
cards, break cards, First–Then boards, and access metadata.

## AI ownership

AI may propose concise teacher instructions, plain-language explanations, teaching-flow
descriptions, scenario wording, example variety, personalized activity copy, and artifact
content. OpenAI output is validated with a typed structured-output model before use.

## Compatibility

Old drafts use one adapter in `V2LessonSpecService`. The adapter creates explicit legacy
decision IDs and `legacy_adapter` field resolutions. Missing scheduling or token values are
recorded as `explicit_default` with a reason and confirmation flag. There is no independent
legacy package-generation path after adaptation.

Dedicated printable rendering remains outside this boundary and is not implemented here.
