# Learner Profile Skill

The `learner_profile` skill creates a teacher-reviewable Student Learning Profile draft from selected, parsed records. It is an instructional planning aid, not a diagnosis or clinical assessment.

## Evidence model

Every suggested signal records a category, short summary, evidence type, confidence, source record, optional source location/date, contradiction state, suggested value, review state, and evidence fingerprint. Evidence types distinguish documented facts, teacher/caregiver reports, observations, interpretations, contradictions, outdated evidence, and unknown information. Long record passages are not copied into signals.

The profile covers strengths, interests, communication and response options, receptive/expressive supports, engagement, environmental considerations, motivators, prompting, effective/ineffective supports, independence, mastered/emerging skills, goals, generalization, breaks, barriers, and explicit unknowns.

## Teacher review

Signals can be confirmed, edited, rejected, or left unknown. Existing teacher-confirmed profile fields take precedence during extraction. A rejected or confirmed signal is not replaced by the same evidence fingerprint; new, contradictory, and older evidence remains visible as separate evidence. Confirmed profile snapshots are retained as versions.

Low-confidence interests and motivators are excluded from automatic personalization. Lesson generation receives a minimized profile context and never receives raw record text.

## API

- `GET /api/v2/learners/{id}/profile-extraction`
- `PATCH /api/v2/learners/{id}/profile-signals/{signalId}`
- `POST /api/v2/learners/{id}/profile/confirm`
- `GET /api/v2/learners/{id}/profile/versions`

