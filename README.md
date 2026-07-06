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
cp .env.example .env
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
AI_PROVIDER=mock
ALLOWED_ORIGINS=http://localhost:5173
DATABASE_URL=sqlite:///./autism_copilot.db
DEV_ALLOW_ANON_TEACHER=true
DEV_ANON_TEACHER_ID=1
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2025-01-01-preview
KEY_VAULT_URL=
PEXELS_API_KEY=
PIXABAY_API_KEY=
```

Frontend:

```text
VITE_API_BASE=http://localhost:8000/api
VITE_USE_LOCAL_MOCK=false
```

The browser calls Backend v2 through `VITE_API_BASE`; the backend owns AI
provider selection, credentials, safety checks, and learner-data handling.

## Secrets And Dev Permissions

Backend secrets are read only from environment variables or an ignored
`backend/.env`. Never commit `.env`, paste credentials into source code, bake
them into a Dockerfile, or print them in logs. Only `.env.example` files with
empty placeholders belong in GitHub.

The frontend must never receive OpenAI, Azure OpenAI, Key Vault, search-provider,
or storage secrets. Any variable prefixed with `VITE_` is bundled into browser
JavaScript and is visible to users, so the frontend uses only `VITE_API_BASE`
and the non-secret local-mock flag.

Do not log full learner records, prompts containing learner records, raw AI
responses, or provider exceptions that may contain request metadata. Log only
request IDs, operation names, status, latency, and sanitized error categories.

MVP permission checks use the `X-Teacher-Id` header. For local development,
`DEV_ALLOW_ANON_TEACHER=true` enables an anonymous admin-like teacher so the app
can run without a login system. Production should set this to `false` and replace
the header dependency with real authentication.

## Mock Mode

Mock mode is the default and requires no external services. Backend v2 resolves
providers through a server-side factory. Non-mock v2 providers fail closed when
their secret source or safeguarded adapter is unavailable; learner data is never
silently routed to another provider.

## CORS And Deployment Safety

In development, the backend permits `http://localhost:5173` and
`http://127.0.0.1:5173`. In staging and production it permits only the comma-
separated origins in `ALLOWED_ORIGINS`. Use exact HTTPS origins in production;
do not configure `*` with credentialed requests.

The future Azure deployment should use Managed Identity to read Azure OpenAI
credentials or connection metadata from Azure Key Vault (`KEY_VAULT_URL`). App
Service or Container Apps receives identity-based access; GitHub Actions and
container images should not contain long-lived API keys. Key Vault retrieval,
minimum-data prompts, audit-safe telemetry, and provider safety controls must be
implemented before enabling the Azure Backend v2 adapter.

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
py -m pytest

cd frontend
npm run build
```

Current status: backend tests pass and frontend production build passes.

## Azure Deployment Direction

- Database: PostgreSQL Flexible Server or Azure SQL
- Storage: Azure Blob Storage
- API: Azure App Service or Azure Container Apps
- Frontend: Azure Static Web Apps
- AI: Azure OpenAI through `AzureOpenAIProvider`

## Remaining TODOs

- Add migrations with Alembic before real production data.
- Add user authentication, teacher/team boundaries, and privacy controls.
- Add API endpoints to list historical lesson packages and session records.
- Add file/blob storage for uploaded and generated image assets.
- Add richer progress history views and goal-level trend summaries.

## Recommended Next Priorities

1. Add Alembic migrations and PostgreSQL CI coverage.
2. Build dedicated teaching-goal CRUD and connect goals to session records.
3. Add teacher review workflow for candidate images and lesson package approval.
4. Add privacy-safe export for teaching packages and data sheets.
