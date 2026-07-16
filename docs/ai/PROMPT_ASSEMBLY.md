# Prompt assembly and trust boundaries

`PromptBuilder` creates two separate messages.

The system instructions contain only:

1. the global safety boundary;
2. the selected skill role;
3. versioned instructional quality rules;
4. versioned task instructions;
5. the output contract;
6. prohibited behavior.

The user input contains trusted minimized application fields and a separately labeled `untrustedContent` object inside `UNTRUSTED_CONTENT` delimiters.

Uploaded document text, teacher free text, and externally sourced text must never be interpolated into system instructions. They remain data even if they contain text such as “ignore previous instructions.” Provider code sends the two prompt fields separately.

Before profile extraction, record text is already size-limited and wrapped by the upload security service. Lesson generation receives a minimized learner context rather than raw records. Logs contain operation names and stable error codes, not complete prompts, model responses, or student records.

Examples in skill files are synthetic and should not contain real learner data.
