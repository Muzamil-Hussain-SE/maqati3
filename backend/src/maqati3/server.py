"""The production wiring: settings from the environment, real implementations of every
boundary, one connection pool. `create_app` stays the single place routes are mounted;
this module only decides what is plugged into it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from psycopg_pool import ConnectionPool
from pydantic_settings import BaseSettings, SettingsConfigDict

from maqati3.api.app import create_app
from maqati3.db.library import PgLibraryRepository
from maqati3.db.sql import PooledExecutor
from maqati3.db.submissions import PgFingerprintIndex, PgKnownHashes, PgSubmissions
from maqati3.dedup.chromaprint import ChromaprintExtractor
from maqati3.staging import DEFAULT_MAX_BYTES, LocalUploadStore

#: The repository root, for the defaults below: backend/src/maqati3/server.py -> repo.
_REPO = Path(__file__).resolve().parents[3]

#: How often the running server clears uploads nobody decided on.
SWEEP_INTERVAL_S = 30 * 60

log = logging.getLogger("maqati3")


def sweep_staging(submissions: PgSubmissions, store: LocalUploadStore) -> int:
    """Delete uploads left undecided past their time, and their staged files."""
    paths = submissions.sweep()
    for path in paths:
        try:
            store.discard(path)
        except ValueError:
            # A path outside staging came out of the database. Never delete it; say so.
            log.warning("swept submission pointed outside staging: %s", path)
    if paths:
        log.info("swept %d abandoned upload(s)", len(paths))
    return len(paths)


def sweep_abandoned(app: FastAPI) -> int:
    """`sweep_staging` with the running app's own store and submissions."""
    return sweep_staging(app.state.submissions, app.state.store)


class Settings(BaseSettings):
    """Read from the environment (and a local .env). See .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    #: The credential the unlisted upload link carries (in its #fragment). Long and
    #: random -- `python -c "import secrets; print(secrets.token_urlsafe(24))"`.
    #: Changing it revokes every link handed out with the old one.
    upload_key: str = ""
    staging_dir: Path = Path("/var/lib/maqati3/staging")
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

    async def sweep_forever(app: FastAPI) -> None:
        while True:
            try:
                await asyncio.to_thread(sweep_abandoned, app)
            except Exception:  # a failed sweep must not take the server down
                log.exception("sweeping abandoned uploads failed")
            await asyncio.sleep(SWEEP_INTERVAL_S)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool.open(wait=True)
        sweeper = asyncio.create_task(sweep_forever(app))
        try:
            yield
        finally:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper
            pool.close()

    executor = PooledExecutor(pool)
    store = LocalUploadStore(settings.staging_dir, max_bytes=settings.max_upload_bytes)
    submissions = PgSubmissions(executor)
    app = create_app(
        PgLibraryRepository(executor),
        store=store,
        extractor=ChromaprintExtractor(fpcalc=settings.fpcalc_path),
        index=PgFingerprintIndex(executor),
        hashes=PgKnownHashes(executor),
        submissions=submissions,
        lifespan=lifespan,
        upload_key=settings.upload_key,
    )
    app.state.store = store
    app.state.submissions = submissions
    return app


__all__ = ["Settings", "build_app", "sweep_abandoned", "sweep_staging"]
