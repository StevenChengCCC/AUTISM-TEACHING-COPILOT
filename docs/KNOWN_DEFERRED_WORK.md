# Known deferred work

These items are deliberately outside the completed demonstration rounds or
require AWS execution evidence that source code cannot provide. They must not be
described as implemented, certified, compliant, or production-ready.

## Cloud verification still required

- Execute the full Cognito + Amplify + Elastic Beanstalk acceptance journey.
- Run PostgreSQL-specific integration tests against a disposable PostgreSQL
  database and verify Alembic upgrade/downgrade in the target engine.
- Verify RDS encryption, backups, retention, deletion protection, networking,
  and a safe temporary restore drill.
- Verify S3 Block Public Access, encryption, ownership, lifecycle, versioning,
  anonymous denial, and version recovery in the staging account.
- Deploy/test CloudWatch metric filters, RDS/ALB alarms, log retention, and SNS
  delivery.
- Verify restart and same-version redeploy persistence with representative
  synthetic resources.

## Document pipeline

- OCR provider/workflow for scanned or image-only PDFs remains deferred;
  teachers must paste/correct text.
- A formal malware scanning service is not configured. The product reports
  `malwareScanStatus=not_configured` and must not claim files were scanned.
- Additional formats, corrupted-file repair, very large document processing,
  asynchronous parsing queues, and quarantine operations at scale are deferred.
- Data-loss prevention, content-disarm/reconstruction, and forensic file
  analysis are not implemented.

## AI and instructional quality

- Instructional prompts/skills need ongoing expert source review, evaluation,
  bias/error analysis, regression datasets, and controlled version governance.
- Generated content does not diagnose, prescribe treatment, replace teacher or
  BCBA judgment, or promise outcomes.
- Current safety and standards checks are instructional guidance, not legal or
  district compliance checks.
- Provider redundancy, quota automation, cost controls, advanced moderation,
  adversarial testing, and human escalation operations are deferred.
- Image generation/search candidates still require explicit teacher review,
  licensing review, and safety review.

## Scale and reliability

- Inline parsing/export/generation should move to durable asynchronous workers
  (for example SQS-backed jobs) before meaningful scale.
- Multi-region recovery, cross-region database replicas, cross-region S3
  replication, formal RTO/RPO, load/soak tests, autoscaling tests, and chaos
  testing are deferred.
- The 30-day suggested log retention and 7-day demo export/backup settings need
  an approved organizational retention policy before real use.
- S3 recovery depends on versioning being enabled and noncurrent versions still
  being retained.

## Authentication and administration

- The implementation supports a small demo organization; enterprise tenant
  administration, teacher invitation lifecycle, role/permission management,
  identity federation, MFA enforcement, account recovery operations, and full
  revocation/session inventory are deferred.
- Formal authorization review, penetration testing, threat modeling, WAF/rate
  limits, abuse detection, SIEM integration, and security incident operations
  are deferred.
- Minimized audit events are not a full enterprise audit/compliance system.

## Privacy, legal, and governance

- Do not use real student data until an authorized organization completes its
  privacy/security/legal assessment, agreements, consent/notice analysis,
  retention/deletion policy, subprocessors review, access governance, incident
  plan, and required training.
- No FERPA, HIPAA, COPPA, state-law, district-policy, accessibility, clinical,
  or other legal compliance claim has been established.
- Data subject workflows, legal holds, records retention, data residency,
  eDiscovery, breach notification, and formal deletion verification are
  deferred.
- External image and AI-provider licensing/terms need organizational review.

## Product and accessibility

- Formal accessibility audit/certification, assistive-technology matrix,
  localization, comprehensive tablet/mobile testing, and user research with
  educators are deferred.
- Offline mode, collaborative editing, conflict-resolution UX beyond optimistic
  concurrency, notification workflows, advanced search, analytics, and district
  reporting are deferred.
- Export templates require broader printer, PDF reader, office suite, and
  international paper-size testing.

## Operational ownership

- Name owners for releases, incidents, backups, restore drills, Cognito,
  database, S3, AI-provider usage, and security escalation.
- Establish cost budgets/alerts, credential rotation cadence, dependency
  scanning/patch SLAs, vulnerability response, and service-level objectives.
- Execute rather than merely document the final cloud acceptance and restore
  procedures.

