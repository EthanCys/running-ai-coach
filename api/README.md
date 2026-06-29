# Running AI Coach API

FastAPI backend: data ingestion (COROS MCP + FIT), deterministic metric
calculation, structured report generation, and LLM coach commentary.

> Architecture and decisions: see [../AGENTS.md](../AGENTS.md),
> [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), and [../docs/adr/](../docs/adr/).

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/healthz` | health check |
| POST | `/api/v1/activities/analyze` | analyze a COROS activity (`labelId` + `sportType`) via the COROS MCP |
| POST | `/api/v1/activities/upload`  | analyze an uploaded FIT file (fallback) |

Both analysis endpoints return the same report shape. `/analyze` also returns
`coros_context` and `adjustment_alerts` (L1/L2/L3).

## Service layout

```
app/services/
  fit_parser.py        FIT bytes        → ParsedFitActivity   (adapter)
  coros_adapter.py     COROS MCP JSON   → ParsedFitActivity   (adapter)
  analysis_engine.py   rule layer: deterministic facts
  report_builder.py    facts → structured report JSON
  coach_commentary.py  LLM language layer (+ deterministic fallback)
```

`ParsedFitActivity` is the shared domain model every source maps into; see
[ADR 0003](../docs/adr/0003-shared-domain-model-and-adapters.md).

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env.local
uvicorn app.main:app --reload --port 8000
```

### Configuration (`.env.local`)

- `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` — OpenAI-compatible LLM. If unset,
  the deterministic fallback in `coach_commentary.py` is used.
- `COROS_ACCESS_TOKEN` — only needed when calling the COROS MCP from a standalone
  server. Inside an MCP-capable host the host handles auth.

## Verify

```bash
.venv/bin/python -c "from app.api.routes.activities import router; print('ok')"
```

## Next steps

The single-run analysis works. The next workstream is persistence + user system
+ trends — fully specified in
[../docs/PERSISTENCE-DESIGN.md](../docs/PERSISTENCE-DESIGN.md).
