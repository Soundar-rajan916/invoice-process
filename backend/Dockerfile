# Stage 1: Build dependencies with uv
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.15 /uv /uvx /bin/

COPY pyproject.toml /app/
COPY backend/ /app/backend/
COPY eval/ /app/eval/
COPY mock_accounting/ /app/mock_accounting/
COPY tools/ /app/tools/

WORKDIR /app/backend
RUN uv pip install --system -e . -e /app

# Stage 2: Secure non-root runtime
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:$PATH"

WORKDIR /app

# System dependencies for OpenCV & PyMuPDF (headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -s /bin/sh -m appuser

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

WORKDIR /app/backend
RUN chown -R appuser:appgroup /app

USER appuser:appgroup

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
