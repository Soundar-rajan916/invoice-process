.PHONY: help up down logs migrate seed seed-admin seed-suppliers check test eval gen-data lint typecheck frontend-test invariants whatsapp-setup whatsapp-simulate openwa-key openwa-logs

PYTHON := .venv/bin/python
ifeq ($(OS),Windows_NT)
	PYTHON := .venv/Scripts/python.exe
endif

help:
	@echo "InvoiceFlow Makefile commands:"
	@echo "  make up                 - Start all core Docker services"
	@echo "  make down               - Stop all Docker services"
	@echo "  make logs               - Follow Docker compose logs"
	@echo "  make migrate            - Run database migrations with Alembic"
	@echo "  make seed-admin         - Create initial admin user"
	@echo "  make gen-data           - Generate synthetic invoices"
	@echo "  make seed               - Ingest generated invoices into system"
	@echo "  make check              - Run lint, type-check, backend & frontend tests"
	@echo "  make test               - Run backend test suite with coverage"
	@echo "  make eval               - Run extraction evaluation harness"
	@echo "  make invariants         - Run operational consistency invariant checks"
	@echo "  make whatsapp-setup     - Idempotently configure OpenWA session and webhooks"
	@echo "  make whatsapp-simulate  - Post simulated invoice to WhatsApp webhook"
	@echo "  make openwa-key         - Print OpenWA admin API key from container"
	@echo "  make openwa-logs        - Follow OpenWA container logs"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	cd backend && $(PYTHON) -m alembic upgrade head

seed-admin:
	$(PYTHON) -m backend.app.cli.seed_admin

seed-suppliers:
	$(PYTHON) -m backend.app.cli.seed_suppliers --manifest manifest.jsonl

gen-data:
	$(PYTHON) tools/generate_invoices.py --count 100 --out data/synthetic --seed 42 --faulty-ratio 0.10 --duplicates 5 --multipage-ratio 0.15

seed:
	$(PYTHON) -m backend.app.cli.seed_invoices --dir data/synthetic/pdfs

lint:
	$(PYTHON) -m ruff check backend eval mock_accounting

typecheck:
	$(PYTHON) -m mypy --explicit-package-bases backend/app eval mock_accounting

test:
	$(PYTHON) -m pytest backend/tests -v

eval:
	$(PYTHON) -m eval.run --manifest data/synthetic/manifest.jsonl --inputs data/synthetic/pdfs --extractor mock --limit 200 --out eval/reports/
	$(PYTHON) -m eval.check --report eval/reports/report.json

invariants:
	$(PYTHON) -m backend.app.cli.invariants

frontend-test:
	cd web && npm run test:run

frontend-lint:
	cd web && npm run lint

frontend-build:
	cd web && npm run build

whatsapp-setup:
	$(PYTHON) -m backend.app.cli.whatsapp setup-openwa

whatsapp-simulate:
	$(PYTHON) scripts/simulate_whatsapp_photo.py

openwa-key:
	docker exec invoiceflow_openwa cat /app/data/.api-key

openwa-logs:
	docker compose --profile whatsapp logs -f openwa

check: lint typecheck test invariants frontend-lint frontend-test frontend-build
