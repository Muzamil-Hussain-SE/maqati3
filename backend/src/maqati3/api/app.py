"""Application factory for the public library API."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from maqati3.api.admin import SESSION_COOKIE, SESSION_MAX_AGE_S, AdminConfig
from maqati3.api.admin import router as admin_router
from maqati3.api.repository import LibraryRepository
from maqati3.api.routes import (
    get_extractor,
    get_fingerprint_index,
    get_known_hashes,
    get_repository,
    get_submissions,
    get_upload_key,
    get_upload_store,
    router,
)
from maqati3.api.uploads import KnownHashes, Submissions, UploadStore
from maqati3.dedup.fingerprint import FingerprintExtractor
from maqati3.dedup.triage import FingerprintIndex


def create_app(
    repository: LibraryRepository,
    *,
    store: UploadStore | None = None,
    extractor: FingerprintExtractor | None = None,
    index: FingerprintIndex | None = None,
    hashes: KnownHashes | None = None,
    submissions: Submissions | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
    upload_key: str | None = None,
    admin: AdminConfig | None = None,
) -> FastAPI:
    """Build the API around one implementation of each boundary.

    Every boundary is injected through a dependency override rather than module state,
    so tests and the production wiring use the exact same path. The upload boundaries
    are optional: an app built without them still serves the library, and the upload
    route fails loudly instead of half-working. The same holds for the admin login: an
    app built without `admin` still has the admin routes, and every one answers 503.
    """
    app = FastAPI(title="maqati3", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    app.include_router(admin_router)
    app.state.admin = admin
    app.dependency_overrides[get_repository] = lambda: repository
    if store is not None:
        app.dependency_overrides[get_upload_store] = lambda: store
    if extractor is not None:
        app.dependency_overrides[get_extractor] = lambda: extractor
    if index is not None:
        app.dependency_overrides[get_fingerprint_index] = lambda: index
    if hashes is not None:
        app.dependency_overrides[get_known_hashes] = lambda: hashes
    if submissions is not None:
        app.dependency_overrides[get_submissions] = lambda: submissions
    if upload_key is not None:
        app.dependency_overrides[get_upload_key] = lambda: upload_key
    if admin is not None:
        app.add_middleware(
            SessionMiddleware,
            secret_key=admin.session_secret,
            session_cookie=SESSION_COOKIE,
            max_age=SESSION_MAX_AGE_S,
            same_site="lax",
            https_only=admin.secure_cookie,
        )
    return app
