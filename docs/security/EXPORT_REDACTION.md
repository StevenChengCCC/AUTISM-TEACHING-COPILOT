# Export Redaction and Data Minimization

Teacher handoff exports use allowlisted projections. They do not serialize repository entities wholesale.

## Allowlisted content

- Confirmed learner overview fields needed for instruction.
- Confirmed teaching supports and active goals.
- Progress observations within the teacher-selected dates.
- Selected recent sessions.
- Teacher-approved lesson packages and materials.
- Teacher-authored transition notes.
- Minimal provenance: schema/export versions, generation timestamp, approved-content policy, and AI-assisted-content label.

Generated material content removes `imageBase64`, `providerResponse`, `imagePrompt`, and `rawText` before JSON export. Package projections omit generation metadata, internal provider responses, prompts, and conversations.

## Always excluded by default

- Original learner-record binaries and object keys.
- Extracted and teacher-corrected record text.
- Draft/rejected/superseded packages and materials.
- Internal chat and model prompt content.
- Provider response and evaluator internals.
- Audit logs and request logs.
- Deleted data.
- Secrets, credentials, database URLs, authorization tokens, and storage signatures.
- Contact data that is not needed for this educational handoff.

## ZIP defenses

All member names are server-generated, flattened with `PurePosixPath.name`, rejected when they contain path separators or traversal components, and checked case-insensitively for duplicates. Original filenames are never copied into the ZIP. The object key is a random UUID path and never contains a learner code or name.

## Access and lifecycle

- Artifacts are private objects.
- Download URLs are generated only for completed, unexpired jobs and expire after the configured short TTL.
- Download, completion, failure, and deletion create minimized audit events without learner content.
- Expired artifacts are deleted when accessed/listed; S3 lifecycle rules provide a second deletion layer.
- Manual deletion removes the object before marking the persisted job deleted.

## Verification checklist

- Inspect the ZIP manifest and confirm only selected files exist.
- Search `handoff-data.json` for record text, provider metadata, prompts, and credentials.
- Verify only approved package/material IDs appear.
- Verify progress dates are within the requested range.
- Open CSV in a spreadsheet and confirm formula-like teacher notes remain text.
- Verify a deleted/expired job cannot issue a download URL.

The application does not claim that this workflow alone satisfies FERPA, IDEA, state, district, contractual, or retention requirements. Deployment owners must configure policy and access controls with qualified stakeholders.

