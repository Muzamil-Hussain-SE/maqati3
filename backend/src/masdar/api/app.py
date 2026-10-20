"""Application factory for the public library API."""

from __future__ import annotations

from fastapi import FastAPI

from masdar.api.repository import LibraryRepository
from masdar.api.routes import get_repository, router


def create_app(repository: LibraryRepository) -> FastAPI:
    """Build the API around one repository implementation.

    The repository is injected through a dependency override rather than module state,
    so tests and the production wiring use the exact same path.
    """
    app = FastAPI(title="masdar", version="0.1.0")
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: repository
    return app
