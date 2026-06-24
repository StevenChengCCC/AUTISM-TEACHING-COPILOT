# Autism Teaching Copilot

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
├── api/              # HTTP routes only
├── core/             # config, database, exceptions, logging
├── domain/           # SQLAlchemy models and deterministic engines
├── repositories/     # persistence access
├── services/         # application workflows
├── integrations/     # external AI/API adapters
├── schemas/          # request/response contracts
└── pipelines/        # image asset pipeline

frontend/src/
├── api/              # typed API client
├── components/       # reusable UI
├── hooks/            # reusable state helpers
├── pages/            # product screens
└── types/            # shared TypeScript types
```

## Local Development

Backend:

```bash
cd backend
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

API docs: `http://localhost:8000/docs`

## Environment Variables

Backend:

```text
AI_PROVIDER=mock
DATABASE_URL=sqlite:///./autism_copilot.db
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2025-01-01-preview
PEXELS_API_KEY=
PIXABAY_API_KEY=
```

Frontend:

```text
VITE_API_BASE=http://localhost:8000/api
```

## Mock Mode

Mock mode is the default and requires no external services. Missing OpenAI or Azure OpenAI credentials automatically fall back to `MockProvider`; the app should never crash because API keys are absent.

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
- Persist selected candidate image IDs into teaching packages.
- Add file/blob storage for uploaded and generated image assets.
- Expand frontend into separate pages for child profiles, teaching goals, image pipeline, lesson preview, and session records.
- Add richer progress history views and goal-level trend summaries.

## Recommended Next Priorities

1. Add Alembic migrations and PostgreSQL CI coverage.
2. Build dedicated teaching-goal CRUD and connect goals to session records.
3. Add teacher review workflow for candidate images and lesson package approval.
4. Add privacy-safe export for teaching packages and data sheets.
