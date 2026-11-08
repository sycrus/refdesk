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
#
# Two images from one file. REFDESK_IMAGE picks the last stage, because Render cannot
# choose a build target but passes each environment variable as a build argument:
#   runtime (default)  the full profile, empty store
#   demo               the public demo: read-only profile, the recorded runs from demo/
#   docker build --build-arg REFDESK_IMAGE=demo -t refdesk-demo:dev .
ARG REFDESK_IMAGE=runtime

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
# Debian security updates on top of the pinned base (scan triage, docs/ops/container-scan.md):
# the base image's OS packages lag their fixes. Trade-off: two builds a week apart may
# differ in OS patch level; the scan report records what each build contained.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
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

# --- 4. Demo store (ADR-025, option A) -------------------------------------------------
# Rebuilds the SQLite store from the committed bundle and fetches each image from the
# Met's own image host, checking it against the hash recorded with the run. A changed
# image fails the build. Only Open works; refdesk.demo refuses anything else.
FROM python AS demo-store
COPY demo/ demo/
RUN /app/.venv/bin/python -m refdesk.demo build --bundle demo     --db /out/data/refdesk.sqlite --runs-dir /out/runs --images /out/data/images

# --- 5. Demo image ---------------------------------------------------------------------
FROM runtime AS demo
COPY --from=demo-store --chown=10001:10001 /out/data /app/data
COPY --from=demo-store --chown=10001:10001 /out/runs /app/runs
# Read-only by tag (refdesk/api/profile.py): only read and ops operations answer.
ENV REFDESK_PROFILE=demo     REFDESK_IMAGES_DIR=/app/data/images     REFDESK_AUTO_RESUME=0

# --- Final: runtime or demo ------------------------------------------------------------
FROM ${REFDESK_IMAGE} AS final
