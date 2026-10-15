# EvidenceGuard development image (M3f, ADR-0012). One image for every role: the command selects
# eg-api, eg-worker, eg-admin or alembic. Development only; not a production deployment.
#
# Base images are pinned by digest, verified against their official registries (ADR-0012):
#   python:3.12.14-slim-trixie  (Docker Official Image, Docker Hub)
#   ghcr.io/astral-sh/uv:0.13.0 (Astral, GitHub Container Registry; the uv version CI uses)
# The build context is an allowlist (.dockerignore). No configuration or secrets are baked in.

# --- builder: install the locked, non-dev dependencies and the project as a regular wheel ---------
FROM python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /src

# Dependency layer: only the lockfile inputs, so source edits do not invalidate it.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

# Project layer: --no-editable installs the project as a regular wheel, so the runtime needs no
# source tree.
COPY apps ./apps
COPY packages ./packages
COPY alembic.ini ./
RUN uv sync --locked --no-dev --no-editable

# --- runtime: the virtual environment and the migration configuration only ------------------------
FROM python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS runtime

RUN groupadd --system --gid 10001 evidenceguard \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin evidenceguard

# Files stay owned by root: the runtime user can read but not modify them.
COPY --from=builder --chown=root:root /opt/venv /opt/venv
COPY --chown=root:root alembic.ini /app/alembic.ini

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
USER 10001:10001
EXPOSE 8000

CMD ["eg-api", "--host", "0.0.0.0", "--port", "8000"]
