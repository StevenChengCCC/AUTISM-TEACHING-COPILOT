# Instructional Quality and Safety Rules

Round 5 uses two separate deterministic evaluators. They are instructional guardrails, not legal, clinical, or district compliance certification.

## Instructional quality v1

The versioned evaluator checks observable goals, goal/flow/data alignment, prompting, prompt fading, neutral error correction, reinforcement logic, communication access, dignity, age respectfulness, generalization, material usability, editability, and invented learner information. Every result includes rule ID/version, severity, status, evidence location, explanation, and recommended edit.

Statuses are `pass`, `needs_review`, `blocked`, and `not_applicable`. High-severity failures block approval; review items remain visible to the teacher.

## Instructional safety v1

The safety evaluator blocks punishment, humiliation, deprivation, removal of AAC, forced eye contact, unnecessary physical prompting, restraint, seclusion, aversive practice, diagnosis/cure/medical claims, forced suppression of harmless regulation, and unsupported clinical recommendations.

Safety-blocked packages and their materials cannot be approved. The service never logs the combined content inspected by the rules. Rules use minimized text and safe error messages.

Deterministic phrase checks can produce false positives or miss novel wording. Teacher review and appropriate team escalation remain required.

