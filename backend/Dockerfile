# Build context: the repository root (migrations and reference data live outside backend/).
FROM python:3.13-slim

# fpcalc is the only external tool the upload path needs; it decodes MP4/M4A/Opus/MP3 itself.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev

COPY db/migrations /app/db/migrations
COPY reference /app/reference

ENV MIGRATIONS_DIR=/app/db/migrations \
    REFERENCE_DIR=/app/reference \
    STAGING_DIR=/var/lib/maqati3/staging \
    # Uploads are spooled to a temp file before they are staged; keep that on the volume,
    # not in the container's own filesystem, or a few phone videos fill it.
    TMPDIR=/var/lib/maqati3/tmp \
    PATH=/app/backend/.venv/bin:$PATH

# Migrations and seeding are idempotent, so every start brings the database up to date.
CMD ["sh", "-c", "mkdir -p \"$STAGING_DIR\" \"$TMPDIR\" && python -m maqati3 migrate && python -m maqati3 seed && exec python -m maqati3 serve --host 0.0.0.0 --port 8000"]
