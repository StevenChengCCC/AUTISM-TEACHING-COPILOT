# Known Limitations

- The skills are ready for synthetic usability testing, not clinical validation or autonomous instructional decisions.
- Teacher and appropriate team judgment remain authoritative. The system does not diagnose, prescribe treatment, promise outcomes, or certify legal/district compliance.
- Deterministic phrase-based safety and quality checks cannot recognize every unsafe formulation and may flag benign wording. Blocked or ambiguous output needs human review.
- Profile extraction is limited by parsed record quality. Scanned PDFs may require OCR or teacher correction; absent information remains unknown.
- Evidence page/section and evidence date are only populated when source metadata is available. Current mock extraction generally identifies the record text rather than a page.
- Contradiction and outdated-evidence detection is conservative. The system preserves evidence rather than resolving conflicts automatically.
- Local mock output is deterministic and should not be interpreted as provider quality. Staging/production fail closed rather than silently presenting mock content as AI output.
- Material specifications are print-aware data contracts; final PDF/DOCX/PPTX rendering and accessibility verification remain later work.
- Round 5 does not implement Round 6 capabilities.

