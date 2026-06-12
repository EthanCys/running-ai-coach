# Running AI Coach API

FastAPI backend for workout ingestion, deterministic metric calculation, and report generation.

## Initial Scope

- health check endpoint
- FIT upload endpoint with file persistence and summary parsing
- versioned API routing structure

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate.fish
pip install -e .
uvicorn app.main:app --reload --port 8000
```

## Planned Next Steps

1. Define the normalized activity schema beyond the initial summary fields.
2. Implement the first metric calculators.
3. Persist activities and derived metrics.
4. Add trend and report-generation services on top of parsed workouts.
