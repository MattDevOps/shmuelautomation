# Multistage build for the FastAPI backend, sized for Cloud Run.
#
# Stage 1: Use uv on a build image to install deps into a venv.
# Stage 2: Copy the venv + app source into a slim runtime image.
#
# uv: https://github.com/astral-sh/uv — same dependency manager we use locally.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached layer). --no-install-project skips
# building the package itself, which we copy + install in the next layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Now copy the project and finalize the venv.
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# ─── Runtime image ───────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

# Run as a non-root user. Cloud Run doesn't require this but it's a safe default.
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

# Bring over the installed venv + project from the builder stage.
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

# Cloud Run injects PORT (default 8080). Honour it; default to 8000 for local docker run.
ENV PORT=8000
EXPOSE 8000

# Single-process uvicorn — Cloud Run handles concurrency by spawning more containers.
CMD ["sh", "-c", "uvicorn shmuel_backend.main:app --host 0.0.0.0 --port ${PORT}"]
