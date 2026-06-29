# Running AI Coach

Turns a runner's workout data into a readable, coach-style analysis: a plain
plain-language recap, key findings, risk flags, and one concrete next-run
recommendation — in Chinese.

The core bet: **runners have data but cannot interpret it.** This app is the
bridge between raw watch data and an actionable explanation.

## How it works

- **Primary data source: COROS MCP** — connect your watch account and the app
  reads your activities directly (low friction, no file export).
- **Fallback: FIT file upload** — for platforms without an MCP.
- **Rule layer computes the facts; the LLM only puts them into words.** Numeric
  truth is deterministic and reproducible; the LLM never invents metrics.

## Documentation map

| Doc | What it covers |
|-----|----------------|
| [AGENTS.md](AGENTS.md) | Entry point for AI agents: layout, golden rule, build, conventions |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Current data flow and components (source of truth) |
| [docs/adr/](docs/adr/) | Architecture decision records (why each choice was made) |
| [docs/PERSISTENCE-DESIGN.md](docs/PERSISTENCE-DESIGN.md) | User system, data sync, chat memory, trend analysis |
| [MVP-PRD.md](MVP-PRD.md) | Product scope, users, flows, success metrics |
| [TECHNICAL-SPEC.md](TECHNICAL-SPEC.md) | Long-form system design reference (target state) |

## Project structure

- `api/` — FastAPI backend: data adapters, rule-layer analysis, report + LLM commentary.
- `web/` — Next.js single-page frontend: COROS analysis + FIT upload, report rendering.

## Quick start

Backend:
```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env.local   # fill in LLM + COROS settings (optional)
uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

## Current status

A working **single-run analyser** for both COROS and FIT inputs, with
three-tier (L1/L2/L3) adjustment alerts. It is **stateless** today — cross-run
trends and chat memory (the core PRD value) are designed but not yet built; see
[docs/PERSISTENCE-DESIGN.md](docs/PERSISTENCE-DESIGN.md).
