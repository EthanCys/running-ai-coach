# AGENTS.md

> Entry point for AI coding agents working in this repository.
> Humans: see [README.md](README.md). Architecture rationale: see [docs/adr/](docs/adr/).

## What this project is

Running AI Coach turns a runner's workout data into a readable, coach-style
analysis. The product's core bet: **runners have data but cannot interpret it**;
this app is the bridge between raw watch data and an actionable explanation.

Primary data source is the **COROS MCP** (live watch data, low friction).
FIT file upload is a **fallback** for platforms without an MCP.
The current user-facing product is **chat-first**: connect COROS, ask a coach
question, and receive a grounded explanation plus an optional report card.

## Golden rule (do not break)

**The rule layer computes facts. The LLM only translates facts into language.**

- Numeric truth (pace fade, HR drift, fatigue risk, training type) is produced by
  deterministic Python in `analysis_engine.py` / `report_builder.py`.
- The LLM (`coach_commentary.py`) may only rephrase those facts. It must never
  invent metrics, override calculations, or make medical claims.
- If the LLM is unavailable, a deterministic fallback produces the same report
  shape. Never make the report depend on the LLM being up.

See [docs/adr/0001-rule-layer-first.md](docs/adr/0001-rule-layer-first.md).

## Repository layout

```text
running-ai-coach/
├── AGENTS.md              ← you are here
├── README.md              ← human-facing overview
├── MVP-PRD.md             ← product scope & requirements
├── TECHNICAL-SPEC.md      ← system design reference
├── wiki.repo              ← short AI handoff summary
├── docs/
│   ├── ARCHITECTURE.md    ← current data flow (source of truth)
│   └── adr/               ← architecture decision records
├── api/                   ← FastAPI backend
│   └── app/
│       ├── api/routes/auth.py         ← COROS OAuth session flow
│       ├── api/routes/chat.py         ← chat entrypoint
│       ├── api/routes/activities.py   ← /upload (FIT) + /analyze (COROS)
│       ├── services/
│       │   ├── fit_parser.py          ← FIT → ParsedFitActivity
│       │   ├── coros_adapter.py       ← COROS MCP → ParsedFitActivity
│       │   ├── chat_orchestrator.py   ← intent routing + report card assembly
│       │   ├── analysis_engine.py     ← rule layer: facts
│       │   ├── report_builder.py      ← structured report
│       │   ├── coach_commentary.py    ← LLM language layer (+ fallback)
│       │   └── history_store.py       ← lightweight same-type training history
│       └── schemas/activities.py      ← pydantic response contracts
└── web/                   ← Next.js frontend (single page app)
    └── src/app/page.tsx
```

## Data flow

Primary chat path:

```text
browser → auth.py → chat.py → chat_orchestrator.py → coros_client.py / coros_adapter.py
    → ParsedFitActivity → analysis_engine.py → report_builder.py → coach_commentary.py
    → chat reply + optional report card
```

Fallback FIT path:

```text
FIT upload → activities.py → fit_parser.py → ParsedFitActivity → analysis_engine.py
      → report_builder.py → coach_commentary.py → JSON response
```

`ParsedFitActivity` is still the **shared domain model**. Any new data source
must map into it before entering the rule layer.

## Build & run

Backend:

```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8010
```

Frontend:

```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

## Verify before you claim done

```bash
# backend imports compile
cd api && .venv/bin/python -c "from app.api.router import api_router; print('ok')"

# frontend type-checks / lints
cd web && npm run lint && npm run build
```

There is no test suite yet. If you add logic to the rule layer, add a test
(pytest is the expected choice — see ADR 0001 for why the rule layer is the
part that most needs tests).

## Conventions

- Python: type hints everywhere, `from __future__ import annotations`,
  dataclasses with `slots=True` for domain models, no external state in services.
- Services are pure functions where possible: `(input) -> dict`. Keep I/O
  (HTTP, file, env) at the route layer or in clearly named helpers.
- Chinese is the user-facing output language. Code, comments, and identifiers
  stay in English.
- The frontend is thin by design. Put workout truth and coaching logic in backend
  services, not in `page.tsx`.
- Do not add a dependency without pinning a version range in `pyproject.toml`.

## Known gaps (good first contributions)

1. **No real multi-user persistence** — there is lightweight local history and
  disk-backed OAuth session storage, but no real user identity model or DB.
2. **History is MVP-grade** — `history_store.py` writes JSONL with a default
  local user path, which is useful for longitudinal prompting but not a full
  trend engine.
3. **COROS context is still incomplete** — some L1/L2/L3 signals should be
  auto-fetched server-side instead of relying on caller-provided context.
4. **No tests** on the core rule layer.
