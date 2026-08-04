# Privacy-safe usability measurement

Telemetry is off by default. The product exposes the local study panel only in development builds and requires participant opt-in. Production collection remains disabled unless a separate privacy/security review and deployment approval occurs.

Allowed fields are schema version, random event ID, pseudonymous participant ID, synthetic case ID, milestone/task code, timestamp, duration, interaction count, 1–5 rating, outcome code, and predefined error category.

Never collect learner or teacher names, direct learner IDs, record text, lesson content, notes, document names, prompts, PDF contents, credentials, signed URLs, full URLs, keystrokes, or session replay.

Default retention is 30 days. The local panel can export the participant’s JSON and delete local events. A facilitator must delete the export and local copy after analysis or when the participant withdraws. The backend test sink supports participant-scoped export, deletion, and expiry purge.
