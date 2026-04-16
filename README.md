# KatalogAI

<p align="center">
  <a href="https://github.com/katalogai/katalogai/actions">
    <img src="https://github.com/katalogai/katalogai/actions/workflows/ci.yml/badge.svg" alt="CI Status">
  </a>
  <a href="https://github.com/katalogai/katalogai/actions">
    <img src="https://github.com/katalogai/katalogai/actions/workflows/deploy.yml/badge.svg" alt="Deploy Status">
  </a>
  <a href="https://pypi.org/project/katalogai/">
    <img src="https://img.shields.io/pypi/v/katalogai.svg" alt="PyPI Version">
  </a>
  <a href="https://pepy.tech/project/katalogai">
    <img src="https://pepy.tech/badge/katalogai" alt="Downloads">
  </a>
  <a href="https://github.com/katalogai/katalogai/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/katalogai/katalogai.svg" alt="License">
  </a>
</p>

> AI-powered product catalog management with intelligent HSN code assignment and ONDC integration.

KatalogAI extracts structured product data from unstructured text and product images, assigns correct HSN (Harmonized System of Nomenclature) codes using semantic search, and formats output for ONDC (Open Network for Digital Commerce) protocol. Designed primarily for Indian retail (kirana stores), but adaptable to any retail context.

## Features

- **Multi-Source Data Extraction**: Extract product data from free-form text and product images
- **AI-Powered OCR**: PaddleOCR + Google Gemini for accurate image-based extraction
- **HSN Code Assignment**: Semantic similarity search using pgvector embeddings
- **Confidence Scoring**: Per-field confidence scores with weighted aggregation
- **Human-in-the-Loop**: Review workflow for low-confidence extractions
- **ONDC Ready**: Native output in ONDC catalog item format
- **Multi-Tenant**: API key-based tenant isolation with rate limiting

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         KatalogAI                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Text       │    │   Image      │    │   Review     │     │
│  │   Ingestion  │    │   Ingestion  │    │   Workflow   │     │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘     │
│         │                   │                   │              │
│         ▼                   ▼                   ▼              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Extraction Pipeline                        │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │  Regex  │→ │ Gemini  │→ │   HSN   │→ │Confidence│   │   │
│  │  │ Parser  │  │   VLM   │  │ Search  │  │  Score  │   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    ONDC Output                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────┐
│  PostgreSQL │   │    Redis    │   │  pgvector   │   │  Sentry │
│  (Primary)  │   │   (Queue)   │   │  (HSN Vectors)│  │ (Monitor)│
└─────────────┘   └─────────────┘   └─────────────┘   └─────────┘
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI 0.115+ |
| **Language** | Python 3.12+ |
| **Database** | PostgreSQL 16 (async SQLAlchemy 2.0) |
| **Vector Search** | pgvector |
| **Cache/Queue** | Redis (ARQ) |
| **AI/ML** | Google Gemini 2.0 Flash, PaddleOCR, Sentence-Transformers |
| **Auth** | API Keys (bcrypt) |
| **Monitoring** | Sentry, Prometheus |

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16 with pgvector extension
- Redis 7+
- Google Gemini API key

### Installation

```bash
# Clone the repository
git clone https://github.com/katalogai/katalogai.git
cd katalogai

# Install dependencies
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### Configuration

```bash
# Copy environment file
cp .env.example .env

# Edit .env with your settings
```

Required environment variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `GEMINI_API_KEY` | Google Gemini API key |
| `SECRET_KEY` | Secret key for API key generation |

### Database Setup

```bash
# Run migrations
alembic upgrade head

# Initialize HSN codes (optional - see docs)
python -m app.db.init_db
```

### Run the Server

```bash
# Development
uvicorn app.main:app --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Run with Docker

```bash
docker-compose up -d
```

## API Usage

### Create an API Key

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app", "rate_limit_per_min": 60}'
```

### Ingest Product from Text

```bash
curl -X POST http://localhost:8000/api/v1/ingest/text \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Parle-G biscuits 200g, MRP Rs 30, biscuits"
  }'
```

### Ingest Product from Image

```bash
curl -X POST http://localhost:8000/api/v1/ingest/image \
  -H "X-API-Key: your-api-key" \
  -F "file=@product.jpg"
```

### Get Products

```bash
curl -X GET "http://localhost:8000/api/v1/products?page=1&limit=20" \
  -H "X-API-Key: your-api-key"
```

### Review Low-Confidence Fields

```bash
# List pending reviews
curl -X GET http://localhost:8000/api/v1/review \
  -H "X-API-Key: your-api-key"

# Resolve a review
curl -X POST http://localhost:8000/api/v1/review/{id}/resolve \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"value": "confirmed-value", "action": "accept"}'
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ingest/text` | POST | Ingest product from text |
| `/api/v1/ingest/image` | POST | Upload image (async) |
| `/api/v1/products` | GET | List products |
| `/api/v1/products/{id}` | GET | Get product |
| `/api/v1/products/{id}` | PATCH | Update product |
| `/api/v1/jobs/{id}` | GET | Get job status |
| `/api/v1/jobs/{id}/product` | GET | Get product from job |
| `/api/v1/review` | GET | List pending reviews |
| `/api/v1/review/{id}/resolve` | POST | Resolve review item |
| `/api/v1/keys` | POST | Create API key |
| `/health` | GET | Health check |

## Development

### Setup Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
make test

# Run linting
make lint

# Run type checking
make typecheck
```

### Project Structure

```
katalogai/
├── app/
│   ├── api/v1/          # API route handlers
│   │   ├── ingest.py    # Text/image ingestion
│   │   ├── products.py  # Product CRUD
│   │   ├── review.py    # Review workflow
│   │   └── ...
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic request/response models
│   ├── services/        # Business logic (no FastAPI imports)
│   ├── ml/              # ML components
│   │   ├── text_parser.py   # Regex extraction
│   │   ├── vlm.py           # Gemini integration
│   │   ├── ocr.py           # PaddleOCR wrapper
│   │   ├── confidence.py    # Confidence aggregation
│   │   └── hsn/             # HSN code search & verification
│   ├── workers/         # ARQ background tasks
│   ├── db/              # Database setup & migrations
│   └── core/            # Security, exceptions, config
├── tests/               # Unit & integration tests
├── docker/              # Docker configuration
├── alembic.ini          # Migration config
└── pyproject.toml       # Project metadata
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: https://github.com/katalogai/katalogai/issues
- **Discussions**: https://github.com/katalogai/katalogai/discussions

## Acknowledgments

- [ONDC](https://ondc.org/) for the protocol specifications
- [Google Gemini](https://gemini.google.com/) for AI capabilities
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) for OCR
- [pgvector](https://github.com/pgvector/pgvector) for vector similarity search