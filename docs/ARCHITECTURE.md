# Architecture

This file is the current technical source of truth.

Use it for how the system works now.
Use [adr/](adr/) for why decisions were made.
Use [PERSISTENCE-DESIGN.md](PERSISTENCE-DESIGN.md) for the longer-term storage plan.

## System summary

Running AI Coach currently has two ingestion paths:

- COROS OAuth + MCP-backed analysis
- FIT upload fallback

Both paths converge on one shared domain model and one downstream pipeline:

`source -> parsed activity -> deterministic analysis -> deterministic report -> LLM commentary`

The main product flow is now chat-first, not upload-first.

## Runtime shape

### Frontend

The frontend is a single-page Next.js app in [web/src/app/page.tsx](/home/ethan/work/projects/running-ai-coach/web/src/app/page.tsx).

Its responsibilities are intentionally thin:

- initiate COROS OAuth
- restore a saved COROS session from `localStorage`
- send chat messages to the backend
- render assistant replies, recent record lists, and structured report cards

The frontend does not compute training truth.

### Backend

The backend is a FastAPI app in [api/app/main.py](/home/ethan/work/projects/running-ai-coach/api/app/main.py) with three route groups:

- `auth` for COROS OAuth session lifecycle
- `chat` for natural-language coach interaction
- `activities` for direct analysis endpoints

Combined router: [api/app/api/router.py](/home/ethan/work/projects/running-ai-coach/api/app/api/router.py)

## Main flows

### 1. COROS chat flow

```text
browser
  -> /api/v1/auth/coros/login
  -> COROS OAuth callback
  -> browser stores session id
  -> POST /api/v1/chat
  -> chat_orchestrator
  -> coros_client
  -> coros_adapter
  -> ParsedFitActivity
  -> analysis_engine
  -> report_builder
  -> coach_commentary
  -> chat response with reply + optional report card
```

This is the primary user path today.

### 2. FIT upload flow

```text
client
  -> POST /api/v1/activities/upload
  -> fit_parser
  -> ParsedFitActivity
  -> analysis_engine
  -> report_builder
  -> coach_commentary
  -> structured activity response
```

This remains useful as a fallback path and a backend test surface.

## Core components

### Shared domain model

The architectural center is `ParsedFitActivity`.

Why it matters:

- COROS data and FIT data are normalized into the same shape
- the rule layer stays independent from source-specific payloads
- new data sources should adapt into this model instead of bypassing it

Important nested data includes:

- summary/session fields
- lap list
- segment list
- metric bundle
- per-km split data where available

### COROS integration

[api/app/services/coros_client.py](/home/ethan/work/projects/running-ai-coach/api/app/services/coros_client.py) is the thin HTTP/JSON-RPC wrapper over COROS MCP.

[api/app/services/coros_adapter.py](/home/ethan/work/projects/running-ai-coach/api/app/services/coros_adapter.py) maps COROS payloads into the shared model and optional context.

COROS context is a side channel for signals such as:

- recovery percent
- sleep HRV
- resting HR
- training load
- L1 alert triggers like `hrv_drop_pct` and `rhr_spike_bpm`

### FIT parsing

[api/app/services/fit_parser.py](/home/ethan/work/projects/running-ai-coach/api/app/services/fit_parser.py) parses FIT files into the same shared activity model.

The parser remains important because it enforces the same downstream contract as COROS.

### Chat orchestration

[api/app/services/chat_orchestrator.py](/home/ethan/work/projects/running-ai-coach/api/app/services/chat_orchestrator.py) is the product-control layer.

It is responsible for:

- detecting coarse user intent
- fetching the right COROS records
- deciding when to analyze the latest run versus list recent runs
- assembling the compact report card included in chat replies

This is deterministic keyword routing, not a general autonomous planner.

### Rule layer

The rule layer lives in [api/app/services/analysis_engine.py](/home/ethan/work/projects/running-ai-coach/api/app/services/analysis_engine.py) and [api/app/services/report_builder.py](/home/ethan/work/projects/running-ai-coach/api/app/services/report_builder.py).

Responsibilities:

- classify training type
- estimate intensity level
- compute EF ratio
- judge recovery quality
- score fatigue risk
- estimate mechanics stability
- build a deterministic Chinese verdict, findings, risks, and next-step recommendation

Important invariant:

- numeric and categorical truth must be computed here, not by the LLM

### Language layer

[api/app/services/coach_commentary.py](/home/ethan/work/projects/running-ai-coach/api/app/services/coach_commentary.py) is the only LLM-calling layer.

Responsibilities:

- package grounded context for the model
- keep prompt rules aligned with the running-coach skill
- produce coach-style Chinese explanation
- fall back deterministically if the model is unavailable or returns unusable output

Current output shape includes:

- `summary`
- `key_findings`
- `strengths`
- `watchouts`
- `next_steps`

## Persistence reality

This repo is no longer fully stateless, but it is still far from a full persistence layer.

Current lightweight storage:

- COROS OAuth sessions persisted to `api/data/coros_sessions.json`
- uploaded FIT files stored under `api/data/uploads/`
- same-type workout history appended to JSONL files under `api/data/history/`

Current limitations:

- no real multi-user identity model
- no durable relational data model
- `history_store` still uses a default local user path for MVP behavior
- no production-grade encrypted token persistence

This means the app has lightweight memory, not full user persistence.

## Current API surface

System:

- `GET /healthz`

Auth:

- `GET /api/v1/auth/coros/login`
- `GET /api/v1/auth/coros/callback`
- `GET /api/v1/auth/coros/status`
- `POST /api/v1/auth/coros/logout`

Chat:

- `POST /api/v1/chat`
- `GET /api/v1/chat/presets`

Activities:

- `POST /api/v1/activities/upload`
- `POST /api/v1/activities/analyze`

## Configuration

Important runtime configuration:

- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL`
- `BACKEND_BASE_URL`
- `WEB_BASE_URL`
- `COROS_ACCESS_TOKEN`

Important local convention:

- the current frontend and OAuth defaults assume backend port `8010`
- older docs and earlier commands may still mention `8000`

If local development behaves inconsistently, check port assumptions first.

## Constraints and likely next bottlenecks

1. The frontend is still a single large page component.
2. The backend has clear domain layering, but limited automated tests.
3. Lightweight history exists, but real multi-user persistence does not.
4. Docs can drift because the project evolved from upload-first MVP to chat-first product.

That makes the next likely pressure points:

- user identity and history model
- trend analysis over longer windows
- document consolidation and drift control
- rule-layer test coverage
