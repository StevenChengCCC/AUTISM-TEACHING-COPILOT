# Document parsing and safety limitations

This implementation is for synthetic demo records. It does not make the system
ready for real student data.

## Supported parsers

- TXT: UTF-8 or UTF-8 with BOM.
- PDF: selectable text extracted with `pypdf`; normal PDFs are not OCRed.
- DOCX: paragraphs and table cells extracted with `python-docx`; the ZIP package
  must contain `word/document.xml`, macro projects are rejected, and expanded
  package size is bounded.

PDF, DOCX, and TXT extension, declared MIME, and signatures/structure are checked
where practical. This is content validation, not a guarantee that a file is safe.

## Scanned PDFs and low-text documents

If PDF text is below `MIN_EXTRACTED_TEXT_CHARS`, the record becomes `needs_ocr`.
No OCR provider is connected. The teacher can paste/correct text, or delete and
replace the record. Empty content never silently advances into profile extraction.

## Malware scanning

No formal malware-scanning service is connected in this round. The API returns
`malwareScanStatus=not_configured`. It never describes the file as clean or
malware-safe. Before real student records are allowed, add an isolated scanner
workflow, quarantine/promotion states, scanner telemetry, and failure policy.

Do not send learner records to public scanning services by default.

## Deferred capabilities

- OCR for scanned/image-only PDFs and handwriting.
- Password-protected/encrypted-document recovery.
- Legacy `.doc`, RTF, image, spreadsheet, presentation, archive, and email files.
- Semantic layout/table fidelity beyond basic text extraction.
- Formal content-disarm-and-reconstruction.
- Virus/malware scanning and scanner-result attestation.
- Production identity provider and completed organization authorization.
- Legal/compliance certification, retention automation, and deletion assurance.

The original binary is not sent to OpenAI. Extracted text is treated as
untrusted, and profile extraction requires an eligible reviewed/ready record.
