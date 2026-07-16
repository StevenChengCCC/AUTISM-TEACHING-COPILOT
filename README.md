# Lesson Kit Studio

An AI teaching copilot for autism special education teachers. The product helps teachers plan structured 1:1 sessions, manage generalization, choose reinforcement strategies, assemble teaching packages, and track progress over time.

This is not a PowerPoint generator, generic lesson planner, or chatbot. The teacher remains the decision maker; the system is a planning and execution assistant.

## Product Principles

1. Prefer deterministic rules over LLM calls whenever possible.
2. Use AI only for unstructured profile extraction, teacher-facing narrative polishing, image prompt generation, and lesson evaluation.
3. The app must run without API keys. Default mode is mock.
4. Keep the architecture ready for Azure OpenAI, PostgreSQL/Azure SQL, Blob Storage, App Service, and Container Apps.

## Architecture

```text
backend/app/
├── api/              # thin domain routes
├── core/             # config, database, exceptions, logging
├── domain/           # SQLAlchemy models and deterministic engines
├── repositories/     # persistence access
├── services/         # application workflows
├── integrations/     # external AI/API adapters
├── schemas/          # request/response contracts
└── pipelines/        # image asset pipeline

frontend/src/v2/
├── api/              # Backend v2 client and product API façade
├── components/       # reusable Lesson Kit Studio UI
├── pages/            # learner, lesson, output, session, and material views
└── types.ts          # frontend product contracts
```

## Local Development

Backend:

```bash
cd backend
python -m pip install -r requirements.txt
cp .env.example .env.local
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

API docs: `http://localhost:8000/docs`

## Environment Variables

Backend:

```text
APP_ENV=development
APP_VERSION=v2-product
LOG_LEVEL=INFO
AI_PROVIDER=mock
AI_FAILURE_MODE=mock_fallback
ALLOWED_ORIGINS=http://localhost:5173
DATABASE_URL=sqlite:///./autism_copilot.db
TEST_DATABASE_URL=
V2_REPOSITORY_MODE=memory
V2_SEED_SYNTHETIC_DATA=true
RDS_HOSTNAME=
RDS_PORT=5432
RDS_DB_NAME=
RDS_USERNAME=
RDS_PASSWORD=
DEV_ALLOW_ANON_TEACHER=true
DEV_ANON_TEACHER_ID=1
OPENAI_API_KEY=
OPENAI_TEXT_MODEL=gpt-5.5
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_TIMEOUT_SECONDS=60
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2025-01-01-preview
KEY_VAULT_URL=
PEXELS_API_KEY=
PIXABAY_API_KEY=
UNSPLASH_ACCESS_KEY=
```

Frontend:

```text
VITE_API_BASE=http://localhost:8000/api
VITE_USE_LOCAL_MOCK=false
```

The browser calls Backend v2 through `VITE_API_BASE`; the backend owns AI
provider selection, credentials, safety checks, and learner-data handling.

### Runtime modes

| Mode | Intended dependencies | Readiness behavior |
| --- | --- | --- |
| `development` | SQLite, in-memory v2 repository, local storage, anonymous demo teacher, mock AI allowed | Ready, with future deployment capabilities reported as incomplete |
| `test` | Isolated deterministic test dependencies | Ready, with future deployment capabilities reported as incomplete |
| `staging` | PostgreSQL, persistent v2 repository, Cognito, private S3, explicit HTTPS CORS, configured external AI, fail-closed AI errors | Live but not ready until every required capability exists |
| `production` | Same secure capabilities as staging, with production operations and backups | Live but not ready until every required capability exists |

Round 1 provides capability-aware validation rather than pretending later-round
features already exist. A staging or production process can start so operators
can inspect liveness and logs, but `/health/ready` returns HTTP 503 while required
capabilities are incomplete. Do not send user traffic or real learner data to an
environment that is not ready.

External image search is optional and follows internal approved asset lookup.
`PEXELS_API_KEY` enables the Pexels photo search adapter; `PIXABAY_API_KEY` and
`UNSPLASH_ACCESS_KEY` are reserved for placeholder adapters. Missing keys return
no external results and never prevent the backend from starting. These keys stay
in backend environment variables and are never returned to the frontend.

`IMAGE_ASSET_STRATEGY=generate_first` is the demo default: reusable generated
or approved assets are checked first, then key visual materials request a new
teacher-reviewable image, with external and internal assets as safe fallbacks.
Set `IMAGE_ASSET_STRATEGY=reuse_search_generate` for a lower-cost mode that
prefers reusable and external candidates before generation. Package generation
never creates images for data sheets or summary templates.

## Using AWS RDS PostgreSQL

Local development uses SQLite by default:

```text
DATABASE_URL=sqlite:///./autism_copilot.db
```

AWS Elastic Beanstalk demo deployments should use RDS PostgreSQL for persistent
backend data. If you attach an Elastic Beanstalk integrated RDS database, AWS can
provide these environment variables to the backend:

```text
RDS_HOSTNAME=
RDS_PORT=5432
RDS_DB_NAME=
RDS_USERNAME=
RDS_PASSWORD=
```

When `DATABASE_URL` is still the default SQLite URL and all `RDS_*` values are
present, the backend automatically builds:

```text
postgresql+psycopg2://user:password@host:5432/dbname
```

You can alternatively set `DATABASE_URL` directly:

```text
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/dbname
```

Do not expose database credentials to the frontend, do not commit
`backend/.env.local`, and do not print database URLs containing passwords in
logs. Health endpoints intentionally do not return the database URL or password.

For a demo deployment, a small single-AZ PostgreSQL RDS instance is enough. For
production or real student data, use an external/decoupled RDS instance, private
subnets, automated backups, Secrets Manager or another managed secret store,
database migrations, least-privilege database users, and stronger access
controls.

Backend v2 now has a SQLAlchemy repository adapter and Alembic migrations. In
`staging` and `production`, repository selection is forced to SQLAlchemy and no
in-memory fallback is permitted. Local development remains memory-backed by
default; set `V2_REPOSITORY_MODE=sqlalchemy` to exercise durable SQLite locally.

Run local migrations from the repository root:

```bash
alembic -c backend/alembic.ini upgrade head
```

Never run Alembic automatically from every Elastic Beanstalk web instance.
Use the documented one-time migration procedure before directing traffic to a
new application version. See:

- `docs/aws/ROUND_2_RDS_SETUP.md`
- `docs/deployment/DATABASE_MIGRATIONS.md`
- `docs/deployment/RDS_ROLLBACK.md`
- `docs/deployment/STAGING_PERSISTENCE_CHECKLIST.md`

## Secrets And Dev Permissions

Backend secrets are read only from environment variables or an ignored
`backend/.env.local`. Never commit `.env`, paste credentials into source code, bake
them into a Dockerfile, or print them in logs. Only `.env.example` files with
empty placeholders belong in GitHub.

The frontend must never receive OpenAI, Azure OpenAI, Key Vault, search-provider,
or storage secrets. Any variable prefixed with `VITE_` is bundled into browser
JavaScript and is visible to users, so the frontend uses only `VITE_API_BASE`
and the non-secret local-mock flag.

Do not log full learner records, prompts containing learner records, raw AI
responses, or provider exceptions that may contain request metadata. Log only
request IDs, operation names, status, latency, and sanitized error categories.

### Upload security for demo

All learner records and frontend-submitted content are treated as untrusted.
Frontend checks are only convenience; Backend v2 enforces file-name, extension,
content-type, and size validation before creating learner records.

Current demo upload safety:

- Allowed learner record types are TXT, text-based PDF, and DOCX.
- Uploads are limited to 10 MB by default. The browser requests an intent, PUTs
  directly to a private server-selected object key, and confirms completion.
- S3 keys contain random identifiers and a safe extension only; learner codes,
  names, emails, titles, and original filenames are not used in object keys.
- Dangerous double extensions, archives, scripts/executables, SVG/HTML, and
  macro-enabled Office files are rejected.
- Local private development storage is outside the public `/storage` mount;
  staging uses private S3 and short-lived presigned PUT URLs.
- PDF parsing uses selectable text; image-only PDFs become `needs_ocr` and must
  receive OCR later or teacher-entered/corrected text.
- Uploaded files are never executed, imported as code, publicly served, or sent
  as binary files to OpenAI.
- Record text is stripped of unsafe control characters and truncated before AI
  extraction.
- AI extraction treats record text as untrusted and is instructed not to follow
  instructions embedded inside uploaded records.

Formal malware scanning is not configured in this demo. Records explicitly return
`malwareScanStatus=not_configured`; the product never calls them malware-safe or
clean. Before real student records are allowed, add isolated scanning and a
quarantine/promotion workflow. Do not send private learner records to public
scanning APIs by default.

Round 3 setup and limitations:

- `docs/aws/ROUND_3_S3_UPLOAD_SETUP.md`
- `docs/product/DOCUMENT_UPLOAD_FLOW.md`
- `docs/product/DOCUMENT_PARSING_LIMITATIONS.md`
- `docs/deployment/STAGING_UPLOAD_CHECKLIST.md`

MVP permission checks use the `X-Teacher-Id` header. For local development,
`DEV_ALLOW_ANON_TEACHER=true` enables an anonymous admin-like teacher so the app
can run without a login system. Production should set this to `false` and replace
the header dependency with real authentication.

### Using local OpenAI keys safely

OpenAI calls are isolated behind the Backend v2 provider boundary. Development
test endpoints and the main product flow use the same provider abstraction
without exposing the key to the browser or GitHub. Mock remains the local default.

Step 1:

```bash
cp backend/.env.example backend/.env.local
```

Step 2: edit `backend/.env.local`:

```text
AI_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_TEXT_MODEL=gpt-5.5
OPENAI_IMAGE_MODEL=gpt-image-2
```

Step 3: restart the backend.

Never put `OPENAI_API_KEY` in frontend environment files or create a
`VITE_OPENAI_API_KEY`; Vite variables are public browser code. Never commit
`backend/.env.local`. In production, use a managed secret store such as Azure
Key Vault with Managed Identity instead of a checked-in key.

### Development AI text checks

These endpoints are available only when `APP_ENV=development`. They return a
boolean indicating whether a key exists, never the key itself.

AI status:

```bash
curl http://localhost:8000/api/v2/dev/ai-status
```

Test lesson questions:

```bash
curl -X POST http://localhost:8000/api/v2/dev/test-ai-lesson-questions \
  -H "Content-Type: application/json" \
  -d '{"learnerId":"a102","message":"I want to teach asking for help."}'
```

Test lesson package:

```bash
curl -X POST http://localhost:8000/api/v2/dev/test-ai-lesson-package \
  -H "Content-Type: application/json" \
  -d '{"learnerId":"a102","goalText":"Learner will ask for help using a short phrase.","responseLevel":"Short phrase","scenarios":["Toy car stuck","Closed box"],"selectedMaterials":["Visual Cards","Help Card","Token Board","Data Sheet","Summary Template"],"theme":"Vehicles","duration":"10–12 min","customNotes":"Use visual prompt first and token board reinforcement."}'
```

Test image generation (backend development only):

```bash
curl -X POST http://localhost:8000/api/v2/dev/test-image-generation \
  -H "Content-Type: application/json" \
  -d '{"learnerId":"a102","materialType":"visual_card","prompt":"A simple classroom visual card showing a toy car stuck and a child asking for help.","style":"clean printable educational illustration","size":"1024x1024"}'
```

Get internal approved image candidates:

```bash
curl -X POST http://localhost:8000/api/v2/image-assets/candidates \
  -H "Content-Type: application/json" \
  -d '{"concept":"toy car stuck","materialType":"visual_card","learnerId":"a102","maxResults":6,"allowExternalSearch":false,"allowGeneration":false}'
```

List internal image assets:

```bash
curl "http://localhost:8000/api/v2/image-assets?concept=toy%20car"
```

## Mock Mode

Mock mode is the default and requires no external services. Backend v2 resolves
providers through a server-side factory. `AI_FAILURE_MODE=mock_fallback` preserves
the deterministic local demo when a configured provider fails. Staging and
production always enforce fail-closed behavior, returning sanitized
`provider_failure` or `invalid_output` errors instead of realistic mock content.
Missing provider credentials return a sanitized configuration error.

AI instructions are loaded from explicitly versioned skill manifests. See
[`docs/ai/SKILL_ARCHITECTURE.md`](docs/ai/SKILL_ARCHITECTURE.md),
[`docs/ai/SKILL_VERSIONING.md`](docs/ai/SKILL_VERSIONING.md), and
[`docs/ai/PROMPT_ASSEMBLY.md`](docs/ai/PROMPT_ASSEMBLY.md). AWS backend-only
secret injection is described in
[`docs/aws/ROUND_4_AI_SECRET_SETUP.md`](docs/aws/ROUND_4_AI_SECRET_SETUP.md).

## CORS And Deployment Safety

In development, the backend permits `http://localhost:5173` and
`http://127.0.0.1:5173`. In staging and production it permits only the comma-
separated origins in `ALLOWED_ORIGINS`. Use exact HTTPS origins in production;
do not configure `*` with credentialed requests.

## Health, errors, and operational logs

- `GET /health/live` confirms only that the API process is running.
- `GET /health/ready` reports sanitized capability checks and returns HTTP 503
  for an incomplete staging or production environment.
- `GET /api/v2/health` is the stable Backend v2 product health contract.
- `GET /api/v2/dev/ai-status` exposes only provider/model names and a
  `hasApiKey` boolean, and is available only when `APP_ENV=development`.
- Legacy `/health` and `/ready` aliases remain temporarily available.

Every response includes `X-Request-ID`; a valid incoming ID is retained and an
invalid or absent ID is replaced. API errors use `code`, `message`, `retryable`,
`requestId`, optional `fieldErrors`, and the temporary compatibility field
`detail`. Logs are minimized JSON suitable for CloudWatch ingestion. They include
request metadata and sanitized error categories, not authorization headers,
secrets, learner records, documents, prompts, or model responses.

## AWS staging baseline

The backend source is packaged from `backend/` and starts through its `Procfile`.
The Elastic Beanstalk staging environment must eventually provide an HTTPS API
domain such as `https://api-staging.<YOUR_DOMAIN>` and set `APP_ENV=staging`.
Staging readiness remains 503 until every required capability is configured.
PostgreSQL repositories, private S3 adapters, and durable teacher-handoff export
metadata now exist. Production identity and the remaining operational hardening
remain later-round capabilities.

The Vite frontend is present in `frontend/`. The root `amplify.yml` builds it as
an Amplify monorepo application. Configure the Amplify branch with:

```text
AMPLIFY_MONOREPO_APP_ROOT=frontend
VITE_API_BASE=https://api-staging.<YOUR_DOMAIN>/api
VITE_USE_LOCAL_MOCK=false
```

`VITE_API_BASE` is public configuration. Never add database, AWS, Cognito client
secrets, or AI provider keys to Amplify variables. The expected staging frontend
domain is `https://staging.<YOUR_DOMAIN>` (or the Amplify-provided HTTPS domain),
and that exact origin must be the backend `ALLOWED_ORIGINS` value.

The staging architecture expects RDS PostgreSQL, a private S3 bucket, Cognito
OIDC, Secrets Manager injection, explicit CORS, and fail-closed AI behavior.
These integrations exist in code but still require execution and verification
in the target AWS staging account.

The future Azure deployment should use Managed Identity to read Azure OpenAI
credentials or connection metadata from Azure Key Vault (`KEY_VAULT_URL`). App
Service or Container Apps receives identity-based access; GitHub Actions and
container images should not contain long-lived API keys. Key Vault retrieval,
minimum-data prompts, audit-safe telemetry, and provider safety controls must be
implemented before enabling the Azure Backend v2 adapter.

## Demo record and persistence limitations

Backend v2 supports SQLAlchemy/PostgreSQL persistence plus real TXT, selectable-
text PDF, and DOCX parsing. Local development may still explicitly use synthetic
in-memory repositories and local private object storage. Staging requires the
SQLAlchemy repository, PostgreSQL, and private S3; it does not fall back to local
memory/files when those services are unavailable.

Use synthetic or de-identified demo data only. Production identity, malware
scanning, OCR, complete privacy retention/deletion controls, and operational
assurance remain incomplete and are documented as readiness gaps.

For Elastic Beanstalk packaging from the repository root, use:

```bash
cd backend && zip -r ../backend-deploy.zip . -x '.env' '.env.*' '__pycache__/*' '*.pyc' '.venv/*' 'venv/*' 'storage/*' '.pytest_cache/*' '.DS_Store' 'backend-deploy.zip'
```

## Private teacher handoff exports

The v2 backend generates real private ZIP handoff bundles containing a paginated
PDF, formula-safe progress CSV, typed JSON, README manifest, and optional approved
material PDFs. Only confirmed/approved content is projected; original records,
raw extracted text, drafts, conversations, prompts, provider internals, audits,
deleted content, and credentials are excluded by default. Export jobs and history
are persisted, while binary bundles are stored under the private S3 prefix
configured by `S3_EXPORT_PREFIX`.

See:

- [`docs/product/TEACHER_HANDOFF_EXPORT.md`](docs/product/TEACHER_HANDOFF_EXPORT.md)
- [`docs/security/EXPORT_REDACTION.md`](docs/security/EXPORT_REDACTION.md)
- [`docs/aws/ROUND_6_EXPORT_STORAGE.md`](docs/aws/ROUND_6_EXPORT_STORAGE.md)

## Cognito login and AWS frontend deployment

The v2 browser uses Amazon Cognito OIDC Authorization Code Grant with PKCE. It
is a public browser client and must never have an app-client secret. The backend
validates JWT signature, issuer, client ID/audience, token use, and expiration,
then applies the signed user and organization identity to Backend v2 repository
queries. Local development defaults to `AUTH_MODE=demo`; staging and production
use Cognito and cannot use anonymous identity.

The frontend is Vite and uses `VITE_API_BASE`. Copy the safe local templates:

```bash
cp backend/.env.example backend/.env.local
cp frontend/.env.example frontend/.env.local
```

For staging setup see:

- [`docs/aws/ROUND_7_COGNITO_SETUP.md`](docs/aws/ROUND_7_COGNITO_SETUP.md)
- [`docs/aws/ROUND_7_AMPLIFY_DEPLOYMENT.md`](docs/aws/ROUND_7_AMPLIFY_DEPLOYMENT.md)
- [`docs/product/END_TO_END_DEMO_SCRIPT.md`](docs/product/END_TO_END_DEMO_SCRIPT.md)
- [`docs/product/DEMO_TEST_ACCOUNTS.md`](docs/product/DEMO_TEST_ACCOUNTS.md)

Amplify may contain the backend URL, Cognito pool/client/domain identifiers, and
AWS Region. It must never contain OpenAI keys, database passwords, AWS secret
keys, or any other backend-only secret.

## Teaching Package Output

The primary artifact is a teaching package:

- Teaching goal
- Session flow
- Attention-aware segments
- Reinforcement plan
- Generalization plan
- Candidate images
- Teacher script
- Data collection sheet
- Session notes template

## Core Workflow

1. Create or select a child profile.
2. Create or select a teaching goal.
3. Run the image pipeline and let the teacher confirm assets.
4. Generate and save the teaching package with selected image asset IDs.
5. Add a session record after class.
6. Update deterministic progress and goal mastery.

## Deterministic Engines

- Attention engine: segments sessions from attention span.
- Generalization engine: creates plans across visual, object, instructor, environment, and instruction variation.
- Reinforcement engine: creates rotation, schedules, and saturation warnings.
- Progress engine: calculates mastery level, progress delta, and confidence score.

## Image Pipeline

Image sourcing follows this order:

1. Reuse existing approved assets.
2. Search external assets.
3. Generate image candidates/prompts.
4. Teacher reviews.
5. Save approved assets to the library.

Asset metadata includes `source_type`, `concept`, `tags`, `quality_score`, `license_info`, and `reason`-style notes where available.

## Verification

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --disable-warnings

cd frontend
npm run build
```

Current status: backend tests pass and frontend production build passes.

### Round 5 instructional intelligence evaluation

The teacher-assistive learner profile, dynamic lesson planning, typed lesson
package, material schemas, safety rules, quality rules, and approval/version
workflow have a synthetic offline regression gate:

```bash
PYTHONPATH=backend python -m app.evaluation.round5_runner \
  --dataset backend/evaluation/round5_cases.json
```

This command never calls an AI provider and requires no API key. See
[`docs/ai/EVALUATION_PROCESS.md`](docs/ai/EVALUATION_PROCESS.md) and
[`docs/ai/KNOWN_LIMITATIONS.md`](docs/ai/KNOWN_LIMITATIONS.md).

## Azure Deployment Direction

- Database: PostgreSQL Flexible Server or Azure SQL
- Storage: Azure Blob Storage
- API: Azure App Service or Azure Container Apps
- Frontend: Azure Static Web Apps
- AI: Azure OpenAI through `AzureOpenAIProvider`

## Operations, acceptance, and recovery

Round 8 provides the repeatable synthetic-demo operational baseline:

- [`docs/BACKUP_AND_RESTORE.md`](docs/BACKUP_AND_RESTORE.md)
- [`docs/INCIDENT_RESPONSE.md`](docs/INCIDENT_RESPONSE.md)
- [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)
- [`docs/DEMO_ACCEPTANCE_TEST.md`](docs/DEMO_ACCEPTANCE_TEST.md)
- [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md)
- [`docs/KNOWN_DEFERRED_WORK.md`](docs/KNOWN_DEFERRED_WORK.md)
- [`docs/FINAL_READINESS_REPORT.md`](docs/FINAL_READINESS_REPORT.md)

The repository cannot prove that an AWS backup, alarm, bucket control, Cognito
configuration, or restore procedure is active. Those items remain incomplete
until an authorized operator executes the checklists and records evidence. No
destructive restore should ever target active staging.

## Remaining TODOs

- Run the documented Cognito, RDS, S3, Elastic Beanstalk, and Amplify staging actions.
- Add enterprise organization administration, invitations, membership management, and formal privacy controls.
- Move synchronous parsing/export work to durable queues before scaling beyond the demo.
- Add browser-level automated accessibility and multi-device regression coverage.
- Complete production malware scanning/OCR and approved retention automation.
- Execute the CloudWatch alarm tests and an isolated RDS restore drill.

## Recommended Next Priorities

1. Complete the AWS staging checklist and record the Round 8 demo acceptance and isolated restore results.
2. Add enterprise tenant administration and stronger policy-based authorization.
3. Move synchronous parsing/export execution behind SQS and dedicated workers.
4. Complete formal operational, privacy, security, accessibility, and legal review before any real-data use.
