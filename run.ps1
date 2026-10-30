# PowerShell task runner for InvoiceFlow (Windows alternative to make)
param (
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $Python) { $Python = "python" }
}

$env:PYTHONPATH = "$ProjectRoot\backend;$ProjectRoot"

$DockerCompose = "docker compose"
if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $DockerCompose = "docker-compose"
}

switch ($Target.ToLower()) {
    "up" {
        & $DockerCompose up -d
    }
    "down" {
        & $DockerCompose down
    }
    "logs" {
        & $DockerCompose logs -f
    }
    "migrate" {
        Push-Location "$ProjectRoot\backend"
        try {
            & $Python -m alembic upgrade head
        } finally {
            Pop-Location
        }
    }
    "seed-admin" {
        & $Python -m app.cli.seed_admin
    }
    "gen-data" {
        & $Python "$ProjectRoot\tools\generate_invoices.py" --count 100 --out "$ProjectRoot\data\synthetic" --seed 42 --faulty-ratio 0.10 --duplicates 5 --multipage-ratio 0.15
    }
    "seed" {
        & $Python -m app.cli.seed_invoices --dir "$ProjectRoot\data\synthetic\pdfs"
    }
    "lint" {
        & $Python -m ruff check backend eval mock_accounting
        & $Python -m ruff format --check backend eval mock_accounting
    }
    "typecheck" {
        & $Python -m mypy --explicit-package-bases backend/app eval mock_accounting
    }
    "test" {
        & $Python -m pytest backend/tests -v
    }
    "frontend-test" {
        Push-Location "$ProjectRoot\web"
        try {
            npm run test:run
        } finally {
            Pop-Location
        }
    }
    "frontend-lint" {
        Push-Location "$ProjectRoot\web"
        try {
            npm run lint
        } finally {
            Pop-Location
        }
    }
    "frontend-build" {
        Push-Location "$ProjectRoot\web"
        try {
            npm run build
        } finally {
            Pop-Location
        }
    }
    "eval" {
        & $Python -m eval.run --manifest "$ProjectRoot\data\synthetic\manifest.jsonl" --inputs "$ProjectRoot\data\synthetic\pdfs" --extractor mock --limit 200 --out "$ProjectRoot\eval\reports\"
        & $Python -m eval.check --report "$ProjectRoot\eval\reports\report.json"
    }
    "check" {
        Write-Host "Running Ruff lint..." -ForegroundColor Cyan
        & $Python -m ruff check backend eval mock_accounting
        & $Python -m ruff format --check backend eval mock_accounting
        Write-Host "Running Mypy typecheck..." -ForegroundColor Cyan
        & $Python -m mypy --explicit-package-bases backend/app eval mock_accounting
        Write-Host "Running Backend tests..." -ForegroundColor Cyan
        & $Python -m pytest backend/tests -v
        Write-Host "Running Frontend tests & build..." -ForegroundColor Cyan
        Push-Location "$ProjectRoot\web"
        try {
            npm run lint
            npm run test:run
            npm run build
        } finally {
            Pop-Location
        }
    }
    default {
        Write-Host "InvoiceFlow PowerShell task runner" -ForegroundColor Green
        Write-Host "Usage: .\run.ps1 <target>"
        Write-Host ""
        Write-Host "Available targets:"
        Write-Host "  up             - Start Docker containers in background"
        Write-Host "  down           - Stop Docker containers"
        Write-Host "  logs           - Stream container logs"
        Write-Host "  migrate        - Run Alembic database migrations"
        Write-Host "  seed-admin     - Create default admin user"
        Write-Host "  gen-data       - Generate synthetic invoices"
        Write-Host "  seed           - Ingest generated invoices into system"
        Write-Host "  check          - Run lint, type-check, backend & frontend tests"
        Write-Host "  test           - Run pytest suite with coverage"
        Write-Host "  eval           - Run evaluation harness"
        Write-Host "  frontend-test  - Run Vitest tests"
    }
}
