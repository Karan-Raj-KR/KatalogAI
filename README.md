# KatalogAI

<p align="center">
  <strong>AI-powered product catalog management for Indian retail</strong><br>
  Extract structured data from text & images · Auto-assign HSN codes · Export to ONDC
</p>

<p align="center">
  <a href="https://github.com/Karan-Raj-KR/KatalogAI/actions/workflows/ci.yml">
    <img src="https://github.com/Karan-Raj-KR/KatalogAI/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/Karan-Raj-KR/KatalogAI/actions/workflows/deploy.yml">
    <img src="https://github.com/Karan-Raj-KR/KatalogAI/actions/workflows/deploy.yml/badge.svg" alt="Deploy">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  </a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688" alt="FastAPI">
</p>

---

Kirana stores and small retailers often manage inventory with handwritten notes, phone photos, and word-of-mouth. **KatalogAI bridges that gap** — give it a product label photo or a plain-text description, and it returns a fully structured catalog entry with the correct HSN code, confidence scores, and ONDC-ready output.

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [API Usage](#api-usage)
- [API Reference](#api-reference)
- [Development](#development)
- [Contributing](#contributing)

---

## Features

| | |
|---|---|
| **Multi-modal ingestion** | Free-form text or product images (JPG/PNG/WEBP) |
| **AI-powered OCR** | PaddleOCR + Google Gemini 2.0 Flash for accurate label reading |
| **Semantic HSN search** | pgvector embeddings match products to the right HSN code automatically |
| **Confidence scoring** | Per-field scores with weighted aggregation — you know what to trust |
| **Human-in-the-loop** | Review queue surfaces low-confidence fields for manual correction |
| **ONDC-ready output** | Native catalog item format for Open Network for Digital Commerce |
| **Multi-tenant** | API key isolation with per-tenant rate limiting |
| **Async by default** | FastAPI + async SQLAlchemy + ARQ background workers |

---

## How It Works

```
Input (text or image)
        │
        ▼
┌───────────────────┐
│  Text Parser      │  Regex + spaCy extracts name, brand, weight, MRP
│  or OCR + VLM     │  PaddleOCR reads labels; Gemini structures the result
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  HSN Search       │  Sentence-Transformers embed the product description
│                   │  pgvector finds the closest HSN code match
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Confidence Score │  Each field gets a score; low-confidence fields
│                   │  enter the human review queue
└────────┬──────────┘
         │
         ▼
   ONDC Catalog Item  ✓
```

### Example: Text ingestion

**Input**
```
Parle-G biscuits 200g, MRP Rs 30
```

**Output**
```json
{
  "id": "prod_01j...",
  "name": "Parle-G",
  "brand": "Parle",
  "category": "biscuits",
  "weight": "200g",
  "mrp": 30.0,
  "currency": "INR",
  "hsn_code": "1905",
  "confidence": {
    "overall": 0.91,
    "fields": {
      "name": 0.98, "brand": 0.97, "mrp": 0.99,
      "weight": 0.95, "hsn_code": 0.72
    }
  },
  "ondc": { ... }
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        KatalogAI                         │
│                                                          │
│   REST API (FastAPI)                                     │
│   ┌──────────────┬──────────────┬───────────────────┐   │
│   │  /ingest     │  /products   │  /review          │   │
│   │  text/image  │  CRUD        │  human-in-the-loop│   │
│   └──────┬───────┴──────────────┴───────────────────┘   │
│          │                                               │
│   ┌──────▼──────────────────────────────────────────┐   │
│   │              Extraction Pipeline                 │   │
│   │   Regex/spaCy  →  Gemini VLM  →  HSN Search     │   │
│   │                              (pgvector)          │   │
│   └──────────────────────────┬──────────────────────┘   │
│                               │                          │
│   ┌──────────────────────────▼──────────────────────┐   │
│   │           Background Workers (ARQ)               │   │
│   │   Image processing jobs · Async HSN lookups      │   │
│   └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │               │               │
   ┌─────▼─────┐   ┌─────▼─────┐   ┌────▼──────┐
   │ PostgreSQL│   │   Redis   │   │  pgvector  │
   │ (primary) │   │ (queue &  │   │ (HSN embeds│
   │           │   │  cache)   │   │  + search) │
   └───────────┘   └───────────┘   └────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI 0.115+ |
| **Language** | Python 3.12+ |
| **Database** | PostgreSQL 16 · async SQLAlchemy 2.0 · Alembic |
| **Vector Search** | pgvector · Sentence-Transformers |
| **Cache & Queue** | Redis 7 · ARQ |
| **AI / Vision** | Google Gemini 2.0 Flash · PaddleOCR · spaCy |
| **Auth** | API keys · bcrypt |
| **Observability** | Sentry · Prometheus |
| **Packaging** | uv · pyproject.toml |

---

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16 with the `pgvector` extension
- Redis 7+
- Google Gemini API key

### Option A — Docker (recommended)

```bash
git clone https://github.com/Karan-Raj-KR/KatalogAI.git
cd KatalogAI
cp .env.example .env          # fill in your keys
docker-compose up -d
```

The API will be live at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Option B — Local

```bash
git clone https://github.com/Karan-Raj-KR/KatalogAI.git
cd KatalogAI

# Install (uv recommended, pip also works)
pip install -e ".[dev]"

# Configure
cp .env.example .env

# Run migrations & seed HSN codes
alembic upgrade head
python -m app.db.init_db

# Start the server
uvicorn app.main:app --reload
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | Redis DSN (`redis://localhost:6379`) |
| `GEMINI_API_KEY` | Yes | Google AI Studio key |
| `SECRET_KEY` | Yes | Random secret for API key signing |
| `SENTRY_DSN` | No | Sentry project DSN for error tracking |

---

## API Usage

### 1. Create an API key

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app", "rate_limit_per_min": 60}'
```

```json
{ "key": "kat_live_abc123...", "name": "my-app" }
```

### 2. Ingest from text

```bash
curl -X POST http://localhost:8000/api/v1/ingest/text \
  -H "X-API-Key: kat_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"text": "Parle-G biscuits 200g, MRP Rs 30"}'
```

### 3. Ingest from image (async)

```bash
# Upload — returns a job ID
curl -X POST http://localhost:8000/api/v1/ingest/image \
  -H "X-API-Key: kat_live_abc123..." \
  -F "file=@product_label.jpg"

# Poll for completion
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "X-API-Key: kat_live_abc123..."

# Fetch the product once the job is done
curl http://localhost:8000/api/v1/jobs/{job_id}/product \
  -H "X-API-Key: kat_live_abc123..."
```

### 4. List & update products

```bash
# Paginated list
curl "http://localhost:8000/api/v1/products?page=1&limit=20" \
  -H "X-API-Key: kat_live_abc123..."

# Update a field
curl -X PATCH http://localhost:8000/api/v1/products/{id} \
  -H "X-API-Key: kat_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"mrp": 35.0}'
```

### 5. Handle low-confidence reviews

```bash
# List items pending human review
curl http://localhost:8000/api/v1/review \
  -H "X-API-Key: kat_live_abc123..."

# Accept or correct a flagged field
curl -X POST http://localhost:8000/api/v1/review/{id}/resolve \
  -H "X-API-Key: kat_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"value": "1905", "action": "accept"}'
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/ingest/text` | POST | Ingest product from free-form text |
| `/api/v1/ingest/image` | POST | Upload image for async processing |
| `/api/v1/products` | GET | List products (paginated) |
| `/api/v1/products/{id}` | GET | Get a single product |
| `/api/v1/products/{id}` | PATCH | Update product fields |
| `/api/v1/jobs/{id}` | GET | Get background job status |
| `/api/v1/jobs/{id}/product` | GET | Fetch product from a completed job |
| `/api/v1/review` | GET | List pending review items |
| `/api/v1/review/{id}/resolve` | POST | Resolve a review item |
| `/api/v1/keys` | POST | Create an API key |
| `/health` | GET | Health check |

Full interactive docs: `http://localhost:8000/docs`

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
make test

# Lint
make lint

# Type-check
make typecheck
```

### Project Structure

```
katalogai/
├── app/
│   ├── api/v1/              # Route handlers
│   │   ├── ingest.py        # Text & image ingestion endpoints
│   │   ├── products.py      # Product CRUD
│   │   ├── review.py        # Review workflow
│   │   └── keys.py          # API key management
│   ├── ml/                  # ML components
│   │   ├── text_parser.py   # Regex + spaCy extraction
│   │   ├── vlm.py           # Gemini VLM integration
│   │   ├── ocr.py           # PaddleOCR wrapper
│   │   ├── confidence.py    # Per-field confidence scoring
│   │   ├── prompts/         # Gemini prompt templates
│   │   └── hsn/             # HSN code search & verification
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic (no FastAPI imports)
│   ├── workers/             # ARQ background tasks
│   ├── db/                  # DB setup, sessions, init scripts
│   ├── core/                # Security, exceptions, config
│   └── utils/               # Shared utilities
├── tests/                   # Unit & integration tests
├── alembic/                 # Database migrations
├── docker/                  # Docker & compose config
├── docs/                    # Additional documentation
├── scripts/                 # Utility scripts
├── alembic.ini
└── pyproject.toml
```

---

## Contributing

Contributions are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) before opening a PR.

**Quick contribution flow:**

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Run `make lint && make test`
4. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

## Links & Acknowledgments

- **Issues / Bugs**: [github.com/Karan-Raj-KR/KatalogAI/issues](https://github.com/Karan-Raj-KR/KatalogAI/issues)
- **Discussions**: [github.com/Karan-Raj-KR/KatalogAI/discussions](https://github.com/Karan-Raj-KR/KatalogAI/discussions)

Built with [ONDC](https://ondc.org/) protocol specs · [Google Gemini](https://gemini.google.com/) · [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) · [pgvector](https://github.com/pgvector/pgvector)
