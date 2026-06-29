# AGENTS.md

> Entry point for AI coding agents working in this repository.
> Humans: see [README.md](README.md). Architecture rationale: see [docs/adr/](docs/adr/).

## What this project is

Running AI Coach turns a runner's workout data into a readable, coach-style
analysis. The product's core bet: **runners have data but cannot interpret it**;
this app is the bridge between raw watch data and an actionable explanation.

Primary data source is the **COROS MCP** (live watch data, low friction).
FIT file upload is a **fallback** for platforms without an MCP.

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

```
running-ai-coach/
├── AGENTS.md              ← you are here
├── README.md              ← human-facing overview
├── MVP-PRD.md             ← product scope & requirements
├── TECHNICAL-SPEC.md      ← system design reference
├── docs/
│   ├── ARCHITECTURE.md    ← current data flow (source of truth)
│   └── adr/               ← architecture decision records
├── api/                   ← FastAPI backend
│   └── app/
│       ├── api/routes/activities.py   ← /upload (FIT) + /analyze (COROS)
│       ├── services/
│       │   ├── fit_parser.py          ← FIT → ParsedFitActivity
│       │   ├── coros_adapter.py       ← COROS MCP → ParsedFitActivity
│       │   ├── analysis_engine.py     ← rule layer: facts
│       │   ├── report_builder.py      ← structured report
│       │   └── coach_commentary.py    ← LLM language layer (+ fallback)
│       └── schemas/activities.py      ← pydantic response contracts
└── web/                   ← Next.js frontend (single page app)
    └── src/app/page.tsx
```

## Data flow (both entry points converge)

```
COROS MCP  ─┐
            ├─→ ParsedFitActivity ─→ analysis_engine ─→ report_builder ─→ coach_commentary ─→ JSON response
FIT upload ─┘    (shared domain      (rule layer:        (structured       (LLM language +
                  model)              facts)              report)            fallback)
```

`ParsedFitActivity` (defined in `fit_parser.py`) is the **shared domain model**.
Any new data source must map into it; everything downstream is then free.

## Build & run

Backend:
```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

## Verify before you claim done

```bash
# backend imports compile
cd api && .venv/bin/python -c "from app.api.routes.activities import router; print('ok')"

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
- Do not add a dependency without pinning a version range in `pyproject.toml`.

## Known gaps (good first contributions)

1. **No persistence** — every analysis is stateless. Cross-session trends (a
   core PRD value) need a user + activity store. See ADR 0005.
2. **COROS context is manual** — HRV/RHR/recovery signals for L1/L2/L3 are
   passed from the frontend. They should be auto-fetched server-side from the
   MCP. See ADR 0004.
3. **No tests** on the rule layer.
