# refdesk API and UI in one image (issue #167, PRD 13A, ADR-017, ADR-025).
#
# Three stages: build the UI, build the Python environment, then a slim runtime that
# holds only the virtual environment, the config and the built UI. No secrets, no data,
# no model weights and no torch: the build context is an allowlist (.dockerignore), the
# store is created empty at /app/data on first start, and retrieval is the metadata
# baseline (CLIP needs the `embed` extra, which is kept out to fit the free host).
#
# Build and scan run in CI (.github/workflows/container.yml). Locally, with Docker:
#   docker build -t refdesk-api:dev .
#   docker run --rm -p 8000:8000 refdesk-api:dev      then  http://127.0.0.1:8000/healthz

# --- 1. UI ---------------------------------------------------------------------------
FROM node:24.14.0-bookworm-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

# --- 2. Python environment -----------------------------------------------------------
FROM python:3.12.12-slim-bookworm AS python
COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable

# --- 3. Runtime ----------------------------------------------------------------------
FROM python:3.12.12-slim-bookworm AS runtime
RUN groupadd --system --gid 10001 refdesk \
    && useradd --system --uid 10001 --gid 10001 --no-create-home refdesk
WORKDIR /app
COPY --from=python /app/.venv /app/.venv
COPY config/ config/
COPY --from=ui /ui/dist ui/dist
# The only writable place: the SQLite store and run logs. Lost on restart on a free host,
# by design (ADR-025): the demo profile will bake a read-only store into the image.
RUN mkdir -p /app/data /app/runs && chown 10001:10001 /app/data /app/runs
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    REFDESK_DB=/app/data/refdesk.sqlite \
    REFDESK_UI_DIST=/app/ui/dist \
    REFDESK_RETRIEVER=jaccard \
    REFDESK_GENERATOR_TIER=none \
    PORT=8000
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/healthz\", timeout=4)"]
# Render sets PORT; the shell form lets the port follow it.
CMD ["sh", "-c", "exec uvicorn refdesk.api.app:app --host 0.0.0.0 --port ${PORT}"]
