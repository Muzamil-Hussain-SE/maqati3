"""The production wiring: settings from the environment, real implementations of every
boundary, one connection pool. `create_app` stays the single place routes are mounted;
this module only decides what is plugged into it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from psycopg_pool import ConnectionPool
from pydantic_settings import BaseSettings, SettingsConfigDict

from masdar.api.app import create_app
from masdar.db.library import PgLibraryRepository
from masdar.db.sql import PooledExecutor
from masdar.db.submissions import PgFingerprintIndex, PgKnownHashes, PgSubmissions
from masdar.dedup.chromaprint import ChromaprintExtractor
from masdar.staging import DEFAULT_MAX_BYTES, LocalUploadStore

#: The repository root, for the defaults below: backend/src/masdar/server.py -> repo.
_REPO = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Read from the environment (and a local .env). See .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    #: The credential the unlisted upload link carries (in its #fragment). Long and
    #: random -- `python -c "import secrets; print(secrets.token_urlsafe(24))"`.
    #: Changing it revokes every link handed out with the old one.
    upload_key: str = ""
    staging_dir: Path = Path("/var/lib/masdar/staging")
    max_upload_bytes: int = DEFAULT_MAX_BYTES
    fpcalc_path: str = "fpcalc"
    migrations_dir: Path = _REPO / "db" / "migrations"
    reference_dir: Path = _REPO / "reference"
    pool_max_size: int = 10


def build_app(settings: Settings, *, connect_kwargs: Mapping[str, Any] | None = None) -> FastAPI:
    """The app a deployment serves. ``connect_kwargs`` reach every pooled connection --
    the end-to-end test uses them to pin a throwaway schema."""
    if not settings.upload_key.strip():
        # Fail closed: an upload API without its key is an open file drop.
        raise ValueError("UPLOAD_KEY is not set; refusing to serve an open upload API")
    pool: ConnectionPool[Any] = ConnectionPool(
        settings.database_url,
        open=False,
        min_size=1,
        max_size=settings.pool_max_size,
        kwargs=dict(connect_kwargs or {}),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        pool.open(wait=True)
        try:
            yield
        finally:
            pool.close()

    executor = PooledExecutor(pool)
    return create_app(
        PgLibraryRepository(executor),
        store=LocalUploadStore(settings.staging_dir, max_bytes=settings.max_upload_bytes),
        extractor=ChromaprintExtractor(fpcalc=settings.fpcalc_path),
        index=PgFingerprintIndex(executor),
        hashes=PgKnownHashes(executor),
        submissions=PgSubmissions(executor),
        lifespan=lifespan,
        upload_key=settings.upload_key,
    )


__all__ = ["Settings", "build_app"]
