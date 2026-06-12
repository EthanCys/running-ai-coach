# Running AI Coach

This directory contains the initial product definition and implementation plan for a running data analysis product.

Files:

- `MVP-PRD.md`: product scope, target users, user flows, MVP features, success metrics.
- `TECHNICAL-SPEC.md`: system design, data model, metrics engine, APIs, prompt boundaries, and a 4-week build plan.

Project directories:

- `web/`: Next.js frontend scaffold with a project-specific landing page.
- `api/`: FastAPI backend with health check and a working FIT upload plus summary parsing endpoint.

Recommended order:

1. Read `MVP-PRD.md` and confirm scope.
2. Read `TECHNICAL-SPEC.md` and start implementation from the ingestion and analysis pipeline.
3. Start `web` and `api` locally, then build metrics and report generation on top of the working FIT ingestion path.

Quick start:

```bash
cd web && npm install && npm run dev
```

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate.fish
pip install -e .
uvicorn app.main:app --reload --port 8000
```
