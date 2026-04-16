# Contributing to KatalogAI

Thank you for your interest in contributing!

## Code of Conduct

By participating, you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Local Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for running tests outside Docker)
- An `ANTHROPIC_API_KEY` and `GOOGLE_API_KEY` (see `.env.example`)

### Start with Docker Compose

```bash
git clone https://github.com/katalogai/katalogai.git
cd KatalogAI

cp .env.example .env        # fill in your API keys

docker compose -f docker/docker-compose.yml up --build
```

This starts four services:

| Service  | Port | Purpose                        |
|----------|------|--------------------------------|
| postgres | 5432 | Product catalog database       |
| redis    | 6379 | Job queue (Celery broker)      |
| api      | 8000 | FastAPI application            |
| worker   | —    | Celery worker for async jobs   |

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Run Without Docker (dev loop)

```bash
uv sync --all-extras
uv run uvicorn app.main:app --reload        # API
uv run celery -A app.worker worker -l info  # Worker (separate terminal)
```

---

## Running Tests

```bash
make test          # full suite
make test-unit     # unit tests only (no external services needed)
make lint          # ruff + mypy
```

---

## Codebase Map

```
app/
  api/          # FastAPI routers and request/response schemas
  ml/
    agent/      # Claude-powered agentic pipeline
      orchestrator.py   # main agent loop
      tools.py          # tool definitions (OCR, HSN lookup, …)
      prompts.py        # system + user prompt templates
    ocr.py      # Gemini Vision OCR wrapper
    vlm.py      # multimodal embedding / VLM helpers
  services/
    ingestion_service.py  # coordinates ML → DB pipeline
  models/       # SQLAlchemy ORM models
  db/           # database session and migrations (Alembic)
scripts/
  reference_data.csv  # HSN code reference table
tests/
  unit/         # fast, no-IO tests
  integration/  # require running Postgres + Redis
```

The agent entry point is [app/ml/agent/orchestrator.py](app/ml/agent/orchestrator.py). New tools go in [app/ml/agent/tools.py](app/ml/agent/tools.py) and need a corresponding prompt update in [app/ml/agent/prompts.py](app/ml/agent/prompts.py).

---

## Pull Request Workflow

1. Fork the repo and create a branch: `git checkout -b feat/my-change`
2. Make changes; add or update tests.
3. Run `make lint && make test` — both must pass.
4. Commit using [Conventional Commits](https://www.conventionalcommits.org/): `feat(agent): add price extraction tool`
5. Open a PR against `main`. One approval required; all CI checks must pass.

---

## Good First Issues

These are well-scoped tasks with clear acceptance criteria — great places to start:

### 1. Write the empty test files

`tests/unit/` contains three stub files with no test bodies yet:

- [tests/unit/test_text_parser.py](tests/unit/test_text_parser.py)
- [tests/unit/test_confidence.py](tests/unit/test_confidence.py)
- [tests/unit/test_hsn_retriever.py](tests/unit/test_hsn_retriever.py)

Pick one, read the corresponding source module, and write `pytest` tests covering the happy path and at least one edge case. No external services needed.

### 2. Add webhook support for job completion

When an ingestion job finishes, optionally `POST` the result to a caller-supplied URL. Suggested approach:

- Add an optional `webhook_url` field to the ingest request schema.
- After the Celery task completes, fire an `httpx.AsyncClient.post` with the job result.
- Add an integration test in [tests/integration/test_ingest_text.py](tests/integration/test_ingest_text.py) using `pytest-httpserver` or `respx` to assert the webhook fires.

### 3. Add more HSN codes to `reference_data.csv`

[scripts/reference_data.csv](scripts/reference_data.csv) is the HSN lookup table used by the agent. It currently covers common kirana categories but is incomplete. Add rows for:

- Packaged drinking water (HSN 2201)
- Spices and condiments (HSN 0904–0910)
- Cleaning supplies / detergents (HSN 3402)

Each row needs: `hsn_code`, `description`, `gst_rate`, `category`. Keep entries consistent with existing formatting.

---

## Questions?

Open an issue for bugs or feature requests, or start a GitHub Discussion for general questions.
