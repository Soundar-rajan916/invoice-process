.PHONY: help up down logs migrate seed seed-admin check test eval gen-data lint typecheck frontend-test

PYTHON := .venv/bin/python
ifeq ($(OS),Windows_NT)
	PYTHON := .venv/Scripts/python.exe
endif

help:
	@echo "InvoiceFlow Makefile commands:"
	@echo "  make up          - Start all Docker services"
	@echo "  make down        - Stop all Docker services"
	@echo "  make logs        - Follow Docker compose logs"
	@echo "  make migrate     - Run database migrations with Alembic"
	@echo "  make seed-admin  - Create initial admin user"
	@echo "  make gen-data    - Generate synthetic invoices"
	@echo "  make seed        - Ingest generated invoices into system"
	@echo "  make check       - Run lint, type-check, backend & frontend tests"
	@echo "  make test        - Run backend test suite with coverage"
	@echo "  make eval        - Run extraction evaluation harness"

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

frontend-test:
	cd web && npm test run

check: lint typecheck test
