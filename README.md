# InvoiceFlow: Production-Quality AI Invoice Processing System

InvoiceFlow is an autonomous, high-accuracy, human-in-the-loop invoice processing platform for distributors handling high-volume supplier invoices via PDF uploads, email attachments, and WhatsApp phone captures.

It extracts key tax and line-item details using Groq's high-speed LPU inference, applies deterministic Indian GST validation and three-layer deduplication, enforces zero-error human review, and idempotently pushes verified records to downstream accounting systems.

---

## 1. System Requirements & Prerequisites

- **Docker & Docker Compose v2** (for containerized PostgreSQL 16, Redis 7, MinIO, Backend, Worker, Mock Accounting, and Frontend)
- **Python 3.12+** (with [uv](https://github.com/astral-sh/uv) or standard virtual environment)
- **Node.js 20+ & npm** (for frontend development and testing)
- **Groq API Key** (required for live LLM extraction; mock extractor mode available for local/CI test without an API key)

---

## 2. Quick Start

### Step 1: Clone and Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and set your `GROQ_API_KEY` (and optionally configure `GROQ_TEXT_MODEL` and `GROQ_VISION_MODEL`).

### Step 2: Start Services
```bash
# On Linux / macOS / Git Bash:
make up

# On Windows PowerShell:
.\run.ps1 up
# Or directly:
docker compose up -d
```
This launches:
- **PostgreSQL 16**: `localhost:5432`
- **Redis 7**: `localhost:6379`
- **MinIO (S3 API & Console)**: `localhost:9000` (API), `localhost:9001` (Web UI)
- **Backend API**: `http://localhost:8000` (Docs at `/docs`)
- **Celery Worker**: Distributed background pipeline
- **Mock Accounting Service**: `http://localhost:8001`
- **React Web Application**: `http://localhost:5173`

### Step 3: Initialize Database & Administrator
```bash
# Run database migrations
make migrate

# Create initial admin user (admin@invoiceflow.local / AdminSecretPassword123!)
make seed-admin
```

### Step 4: Generate Synthetic Invoices & Ingest
```bash
# Generate 100 realistic Indian GST invoices with faults, duplicates, and multipage samples
make gen-data

# Ingest generated invoices into the processing pipeline
make seed
```

Access the web UI at `http://localhost:5173`, log in with `admin@invoiceflow.local`, and begin reviewing invoices in the review queue.

---

## 3. Switching Between Extractors

InvoiceFlow supports two extraction backends configured via `EXTRACTOR` in `.env`:

### Mock Extractor (`EXTRACTOR=mock`)
Used for CI pipelines, automated integration testing, and local development without incurring LLM charges or requiring an external API key. It resolves incoming files against ground truth manifest fixtures.
```bash
EXTRACTOR=mock
MOCK_MANIFEST_PATH=data/synthetic/manifest.jsonl
```

### Groq Extractor (`EXTRACTOR=groq`)
Production pipeline powered by Groq's official Python SDK (`AsyncGroq`). Automatically chooses between:
1. **Text Path (`extraction_path='text'`):** High-speed parsing for digital PDFs with embedded text layers.
2. **Vision Path (`extraction_path='vision'`):** Base64 image payload processing with automatic deskewing, contrast enhancement, and payload budget compression for scanned invoices or mobile photos.

```bash
EXTRACTOR=groq
GROQ_API_KEY=gsk_your_actual_groq_api_key
GROQ_TEXT_MODEL=llama-3.3-70b-versatile
GROQ_VISION_MODEL=llama-3.2-11b-vision-preview
```

---

## 4. Running Tests & Quality Gates

Run the entire verification suite (backend tests, frontend tests, linting, type-checking, and build):
```bash
make check
```

### 4.1 Backend Tests & Code Coverage
```bash
make test
```
Runs `pytest` with coverage report. Test suite enforces a strict **>= 85% line coverage threshold** on `backend/app`.

To run the month-end R4 load simulation (2,000 invoices):
```bash
.venv/bin/pytest backend/tests/test_r4_load.py -m slow -v
```

### 4.2 Frontend Tests & Type Checking
```bash
# Run Vitest unit tests (ReviewDetail form, line-items, decimal.js, override modal)
make frontend-test

# Run TypeScript type check
make frontend-lint

# Build production bundle
make frontend-build
```

### 4.3 End-to-End Smoke Test (Playwright)
```bash
cd web && npm run test:e2e
```

### 4.4 OpenAPI Drift Check
Verify that TypeScript API client definitions match backend route schemas:
```bash
cd web && npm run generate-types:check
```

---

## 5. Evaluation Harness (`eval/`)

InvoiceFlow includes an offline evaluation harness that benchmarks model accuracy and business rule compliance without database side-effects.

```bash
# Run evaluation across synthetic dataset
make eval
```

Or run directly via CLI:
```bash
python -m eval.run \
  --manifest data/synthetic/manifest.jsonl \
  --inputs data/synthetic/pdfs \
  --extractor mock \
  --limit 200 \
  --concurrency 4 \
  --out eval/reports/

# Check metrics against CI thresholds
python -m eval.check --report eval/reports/report.json
```

Reports are exported to `eval/reports/report.json` and human-readable `eval/reports/report.md`.

---

## 6. Repository Layout

```
.
├── backend/
│   ├── app/
│   │   ├── api/            # REST endpoints (auth, files, invoices, admin, metrics, health)
│   │   ├── core/           # Config, logging, security, database session, storage, errors
│   │   ├── models/         # SQLAlchemy 2.0 async models
│   │   ├── schemas/        # Pydantic v2 validation and extraction schemas
│   │   ├── services/       # Business logic (pipeline, validation, dedup, push, state)
│   │   ├── extraction/     # Preprocessing, page grouping, Groq & mock extractors
│   │   ├── ingestors/      # Ingestor protocol & multipart upload ingestor
│   │   └── workers/        # Celery app & async tasks
│   ├── alembic/            # Database migration scripts
│   ├── tests/              # Pytest test suite (>85% coverage)
│   └── pyproject.toml
├── mock_accounting/        # FastAPI mock of downstream accounting system
├── eval/                   # Evaluation CLI, metrics calculation, and CI threshold gate
├── tools/generate_invoices.py   # Ground-truth invoice generator
├── web/                    # React 18 + Vite + TS + Tailwind review UI
├── docs/                   # ARCHITECTURE.md, ASSUMPTIONS.md, RUNBOOK.md
├── docker-compose.yml
├── Makefile
├── .github/workflows/ci.yml
└── .env.example
```

---

## 7. Hard Requirements Compliance (R1–R4)

| Rule | Requirement | Implementation |
|---|---|---|
| **R1** | Blurry/multipage inputs | Laplacian blur rejection (`RESEND_REQUESTED`), OpenCV deskewing, dual text/vision routing, batch merge for multipage documents. |
| **R2** | Zero unreviewed amounts pushed | Database `CHECK` constraint on `PUSHING`/`PUSHED`, immutable `approved_extraction_id`, review revert on unpushed edits, 10-char override reason for remaining errors. |
| **R3** | Supplier duplicate invoices | Layer 1 file SHA-256 hash, Layer 2 business-key partial unique index `(gstin, normalized_invoice_no, financial_year)`, Layer 3 fuzzy match. |
| **R4** | Month-end 4× volume spikes | Celery `acks_late=True` and `prefetch=1`, compare-and-set state transitions, and `GROQ_MAX_CONCURRENCY` semaphore throttling. |

---

## 8. Documentation

- [Architecture & Design Details](docs/ARCHITECTURE.md)
- [Assumptions & Domain Invariants](docs/ASSUMPTIONS.md)
- [Operations & Maintenance Runbook](docs/RUNBOOK.md)
