# Lesson Planning Skill

The `lesson_planning` skill turns a teacher request into a dynamic, concise set of required and conditional questions. It does not use a fixed question count.

Required confirmation includes the observable target and baseline. The runtime can also ask about response modality, contexts, opportunities, duration, prompting start/limits, reinforcement or engagement, neutral error correction, materials, data collection, generalization, and teacher constraints.

The AI may suggest observable wording for a vague request, but the goal remains unconfirmed until the teacher selects or edits it. Recommended options include a short reason and are always editable. Established speech, gesture, picture, sign, and AAC responses remain valid response forms.

`canGenerate` becomes true only when all required questions have a selected or custom answer. Question answers update the typed `LessonDesignDraft`; the page does not know question content in advance.

Provider output is validated against required question groups. Local/test modes may return deterministic `local_mock` content. Staging and production do not silently substitute realistic mock content after provider failure.

