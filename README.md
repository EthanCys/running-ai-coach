# Running AI Coach

Running AI Coach is a Chinese-language running analysis app.

The current product path is:

- connect a COROS account
- ask for a workout review in chat
- get a coach-style explanation grounded in deterministic metrics

FIT upload still exists, but it is now a fallback ingestion path rather than the
main user experience.

## Product idea

The product bet is simple: runners already have data, but most cannot interpret
it. This repo turns workout data into a readable explanation, with:

- training classification
- workload and fatigue signals
- structure-aware interpretation of work and recovery segments
- one concrete next-step recommendation

The key invariant is unchanged:

**the rule layer computes facts; the LLM only turns those facts into language.**

## Current architecture in one paragraph

Two input paths feed one shared analysis pipeline.

- COROS path: OAuth session -> MCP data fetch -> parsed activity -> rule layer -> report -> coach commentary
- FIT path: FIT upload -> parser -> parsed activity -> rule layer -> report -> coach commentary

The frontend is currently chat-first. The backend remains the real system core.

## Repo layout

- `api/` — FastAPI backend for auth, ingestion, analysis, and coach responses.
- `web/` — Next.js frontend for COROS authorization and coach chat.
- `docs/` — architecture, ADRs, and future persistence design.
- `wiki.repo` — short AI-oriented orientation note for this repo.

## Quick start

Backend:

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env.local
uvicorn app.main:app --reload --port 8010
```

Frontend:

```bash
cd web
npm install
npm run dev
```

Notes:

- the frontend defaults to `http://127.0.0.1:8010` for the backend
- COROS OAuth routes also assume backend base `8010` unless overridden by env vars

## What exists today

- COROS OAuth login and session restore
- chat-based coach interface
- deterministic rule-layer analysis
- LLM-backed commentary with deterministic fallback
- FIT upload fallback
- lightweight local history store for same-type workout comparison

## What does not exist yet

- real multi-user persistence
- production-grade token storage
- robust trend engine over long-term history
- automated test coverage for the core rule layer

## Document roles

These explanation files are close to the right limit already, but they were too
overlapping. The intended split is:

- [README.md](README.md): shortest human-facing overview and run instructions
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): current technical source of truth
- [wiki.repo](wiki.repo): 3-minute AI handoff note
- [AGENTS.md](AGENTS.md): working rules for coding agents
- [docs/adr/](docs/adr/): why key architectural decisions were made
- [docs/PERSISTENCE-DESIGN.md](docs/PERSISTENCE-DESIGN.md): future-state persistence plan
- [MVP-PRD.md](MVP-PRD.md): original product scope and rationale
- [TECHNICAL-SPEC.md](TECHNICAL-SPEC.md): original target architecture and build plan

If those boundaries are kept, the file count is acceptable. If they drift back
into restating each other, there are too many.
