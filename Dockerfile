# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Install Python dependencies
FROM python:3.13-slim AS python-deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Pre-install DuckDB extensions so the image ships with them cached.
# At runtime, install_extension() becomes a no-op (already present).
ENV DUCKDB_EXTENSIONS_PATH=/app/.duckdb/extensions
RUN mkdir -p $DUCKDB_EXTENSIONS_PATH && \
    .venv/bin/python -c "import duckdb; conn = duckdb.connect(); conn.execute(\"SET extension_directory='/app/.duckdb/extensions'\"); conn.install_extension('delta'); conn.install_extension('azure'); conn.close(); print('DuckDB extensions cached')"

# Stage 3: Final runtime image
FROM python:3.13-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=python-deps /app/.venv /app/.venv
COPY --from=python-deps /app/.duckdb /app/.duckdb

COPY backend/ ./backend/
COPY main.py alembic.ini entrypoint.sh ./
COPY alembic/ ./alembic/

COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/data/documents /app/data/datasets /app/.duckdb && \
    chown -R appuser:appuser /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DUCKDB_EXTENSIONS_PATH=/app/.duckdb/extensions \
    DEBUG=false

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["./entrypoint.sh"]
