# Learner document upload flow

## Runtime sequence

1. The authenticated teacher asks the backend for an upload intent with learner
   ID, display filename, MIME type, and byte size.
2. The backend checks learner access and metadata, creates a random object key,
   writes an `upload_pending` record, and returns a five-minute presigned PUT.
3. The browser PUTs the binary directly to the private object store and reports
   upload progress. It cannot select the bucket or object key.
4. The browser confirms completion using only learner ID and record ID.
5. The backend verifies the expected stored key and object size, reads at most
   the configured maximum, validates signature/structure, and parses the file.
6. Original object metadata/key remain separate from extracted text and from
   teacher-corrected text in PostgreSQL.
7. The teacher reviews the text. Saving a correction makes that corrected text
   the effective text and marks the record `reviewed`.
8. Profile extraction accepts only `ready` or `reviewed` records with non-empty
   effective text. Binary data is never sent to an AI provider.

## API contracts

```text
POST   /api/v2/learners/{learnerId}/records/upload-intent
PUT    <presigned private URL>
POST   /api/v2/learners/{learnerId}/records/{recordId}/complete
PATCH  /api/v2/learners/{learnerId}/records/{recordId}/extracted-text
DELETE /api/v2/learners/{learnerId}/records/{recordId}
GET    /api/v2/learners/{learnerId}/records
```

The compatibility `POST /records` endpoint accepts teacher-pasted JSON text. It
does not represent a binary upload and records `extraction_method=teacher_paste`.

## State machine

```text
upload_pending -> validating -> parsing -> needs_review -> reviewed
                                      \-> needs_ocr -> reviewed
                                      \-> failed
active deletion -> pending -> deleted
                         \-> failed (retry DELETE)
```

`malwareScanStatus=not_configured` is independent of parsing state. It must not
be relabeled `clean` unless a real scanner produced that result.

## Data minimization

- S3 keys use random UUID segments and the safe extension only.
- Learner codes, names, emails, original filenames, and titles are excluded.
- Original display filenames are metadata only and are sanitized with basename
  semantics/control-character removal.
- Lesson generation uses the reviewed learner profile and confirmed draft, not
  the complete original documents or all extracted text.
- Logs contain request IDs and safe errors, not document bodies or storage URLs.

## Deletion

Delete first marks the row pending, then deletes the private object, clears and
soft-deletes extracted/corrected text, soft-deletes the record, and writes a
minimized audit event. An object-store failure leaves `deletionStatus=failed`;
issuing DELETE again retries the operation.
