"""The admin dashboard's routes: signing in with Google, and an admin's work on uploads.

Three rules hold everything together (CLAUDE.md, "The Admin Workflow"):

* **Fail closed.** Without a configured login every route here answers 503, never
  anything open. The login is built into the app only when `AdminConfig` is given.
* **The admin list is checked on every request**, not only at sign-in, so removing
  someone locks them out at once. The session says who signed in; the list says whether
  they still may.
* **A forged request is not the dashboard's request.** The session cookie is SameSite=Lax
  and HttpOnly, and every state-changing route also demands a header no other site's form
  can set.
"""

from __future__ import annotations

import hmac
import logging
import mimetypes
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, StringConstraints

from maqati3.api.desk import (
    Admins,
    AdminUser,
    DashboardItem,
    Desk,
    NotWaiting,
    ScholarExists,
    UnknownScholar,
)
from maqati3.api.routes import PREVIEW_TYPES, Store
from maqati3.api.schemas import ScholarOut
from maqati3.auth.identity import IdentityError, IdentityProvider

log = logging.getLogger("maqati3")

SESSION_COOKIE = "maqati3_admin"
SESSION_MAX_AGE_S = 7 * 24 * 3600
#: Long enough that a signed cookie cannot be forged by guessing the key.
MIN_SESSION_SECRET = 32

#: Where an admin lands when no (valid) page was named.
DEFAULT_RETURN = "/en/admin"

CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "maqati3"

ADMIN_NOT_CONFIGURED = "admin_not_configured"
ADMIN_LOGIN_REQUIRED = "admin_login_required"
LOGIN_STATE_INVALID = "login_state_invalid"
CSRF_HEADER_MISSING = "csrf_header_missing"
NOT_WAITING = "not_waiting"
UNKNOWN_SCHOLAR = "unknown_scholar"
SCHOLAR_EXISTS = "scholar_exists"

#: A page of ours, as a path. Anything that could leave the site -- a scheme, a second
#: slash, a backslash -- is not accepted, or the login would be an open redirect.
_LOCAL_PATH = re.compile(r"/(?![/\\])[\w\-./?=&%]*")


@dataclass(frozen=True, slots=True)
class AdminConfig:
    provider: IdentityProvider
    admins: Admins
    desk: Desk
    #: The site's own address, e.g. https://archiv.example.org -- what Google redirects
    #: back to, and what decides whether the session cookie is marked Secure.
    public_url: str
    session_secret: str

    def __post_init__(self) -> None:
        if len(self.session_secret) < MIN_SESSION_SECRET:
            raise ValueError(
                f"the session secret must be at least {MIN_SESSION_SECRET} characters"
            )

    @property
    def callback_url(self) -> str:
        return self.public_url.rstrip("/") + "/api/v1/admin/auth/callback"

    @property
    def secure_cookie(self) -> bool:
        return self.public_url.startswith("https://")


def safe_return(value: str | None) -> str:
    """The page to land on after signing in: a local path, or the default."""
    if value is not None and _LOCAL_PATH.fullmatch(value):
        return value
    return DEFAULT_RETURN


def with_login_result(destination: str, result: str) -> str:
    return f"{destination}{'&' if '?' in destination else '?'}login={result}"


# ------------------------------------------------------------------ the gates


def admin_config(request: Request) -> AdminConfig:
    config: AdminConfig | None = getattr(request.app.state, "admin", None)
    if config is None:
        raise HTTPException(status_code=503, detail=ADMIN_NOT_CONFIGURED)
    return config


Config = Annotated[AdminConfig, Depends(admin_config)]


def current_admin(request: Request, config: Config) -> AdminUser:
    """The signed-in admin, re-checked against the list on every request."""
    email = request.session.get("admin")
    admin = config.admins.find(email) if isinstance(email, str) else None
    if admin is None:
        raise HTTPException(status_code=401, detail=ADMIN_LOGIN_REQUIRED)
    return admin


def require_csrf_header(request: Request) -> None:
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=403, detail=CSRF_HEADER_MISSING)


Admin = Annotated[AdminUser, Depends(current_admin)]
#: Order matters: who are you (401) comes before is this really you (403).
Mutating = [Depends(current_admin), Depends(require_csrf_header)]

router = APIRouter(prefix="/api/v1/admin")


# ------------------------------------------------------------------ models


class AdminOut(BaseModel):
    email: str
    name: str | None = None


class RegisteredOut(BaseModel):
    entry_id: str
    scholar: ScholarOut


class DashboardItemOut(BaseModel):
    sha256: str
    original_name: str
    duration_ms: int
    received_at: datetime
    contributor: str | None
    kept_despite: list[str]
    status: Literal["waiting", "registered"]
    entry: RegisteredOut | None
    registered_by: str | None

    @classmethod
    def of(cls, item: DashboardItem) -> DashboardItemOut:
        entry = item.entry
        return cls(
            sha256=item.sha256,
            original_name=item.original_name,
            duration_ms=item.duration_ms,
            received_at=item.received_at,
            contributor=item.contributor,
            kept_despite=item.kept_despite,
            status="waiting" if entry is None else "registered",
            entry=(
                None
                if entry is None
                else RegisteredOut(
                    entry_id=entry.entry_id,
                    scholar=ScholarOut(
                        id=entry.scholar_id,
                        name_ar=entry.scholar_name_ar,
                        name_en=entry.scholar_name_en,
                    ),
                )
            ),
            registered_by=item.registered_by,
        )


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class RegisterIn(BaseModel):
    scholar_id: Text


class RegisterOut(BaseModel):
    entry_id: str


class ScholarIn(BaseModel):
    #: The front of every entry id, and part of URLs: a plain lowercase slug.
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=60)]
    name_ar: Text
    name_en: Text


class StatusOut(BaseModel):
    status: str


# ------------------------------------------------------------------ signing in


@router.get("/auth/login")
def login(
    request: Request, config: Config, return_to: Annotated[str | None, Query(alias="return")] = None
) -> RedirectResponse:
    """Send the browser to Google, remembering what to check when it comes back."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    request.session["oauth"] = {"state": state, "nonce": nonce, "return": safe_return(return_to)}
    url = config.provider.authorization_url(
        redirect_uri=config.callback_url, state=state, nonce=nonce
    )
    return RedirectResponse(url, status_code=303)


@router.get("/auth/callback")
def callback(
    request: Request,
    config: Config,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    # Single use: popped whether or not it matches, so a callback cannot be replayed.
    started = request.session.pop("oauth", None)
    if (
        not isinstance(started, dict)
        or not state
        or not hmac.compare_digest(str(started.get("state", "")).encode(), state.encode())
    ):
        raise HTTPException(status_code=400, detail=LOGIN_STATE_INVALID)
    destination = safe_return(started.get("return"))

    if error or not code:
        return RedirectResponse(with_login_result(destination, "failed"), status_code=303)
    try:
        identity = config.provider.identify(
            code=code, redirect_uri=config.callback_url, nonce=str(started.get("nonce", ""))
        )
    except IdentityError as exc:
        log.warning("admin sign-in refused: %s", exc)
        return RedirectResponse(with_login_result(destination, "failed"), status_code=303)

    admin = config.admins.find(identity.email)
    if admin is None:
        config.admins.log(identity.email, "login_denied", None, {})
        return RedirectResponse(with_login_result(destination, "denied"), status_code=303)

    request.session.clear()
    request.session["admin"] = admin.email
    config.admins.log(admin.email, "login", None, {})
    return RedirectResponse(destination, status_code=303)


@router.post("/auth/logout", dependencies=Mutating)
def logout(request: Request) -> StatusOut:
    request.session.clear()
    return StatusOut(status="signed_out")


@router.get("/me")
def me(admin: Admin) -> AdminOut:
    return AdminOut(email=admin.email, name=admin.name)


# ------------------------------------------------------------------ the dashboard


@router.get("/submissions")
def submissions(config: Config, admin: Admin) -> list[DashboardItemOut]:
    return [DashboardItemOut.of(item) for item in config.desk.items()]


@router.get("/submissions/{sha256}/media")
def media(sha256: str, config: Config, admin: Admin, store: Store) -> FileResponse:
    """An upload's file, for the admin deciding whether it is worth the review time.

    FileResponse answers byte ranges, which is what lets a browser seek in a video. The
    path comes back out of the database; the store decides whether it is a staged file.
    """
    recorded = config.desk.media_path(sha256)
    path = store.locate(recorded) if recorded is not None else None
    if path is None:
        raise HTTPException(status_code=404, detail="media_not_found")
    media_type = PREVIEW_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@router.post("/submissions/{sha256}/register", dependencies=Mutating)
def register(sha256: str, body: RegisterIn, config: Config, admin: Admin) -> RegisterOut:
    try:
        entry_id = config.desk.register(sha256, body.scholar_id, admin.email)
    except NotWaiting as exc:
        raise HTTPException(status_code=409, detail=NOT_WAITING) from exc
    except UnknownScholar as exc:
        raise HTTPException(status_code=422, detail=UNKNOWN_SCHOLAR) from exc
    return RegisterOut(entry_id=entry_id)


@router.post("/submissions/{sha256}/discard", dependencies=Mutating)
def discard(sha256: str, config: Config, admin: Admin, store: Store) -> StatusOut:
    try:
        path = config.desk.discard(sha256, admin.email)
    except NotWaiting as exc:
        raise HTTPException(status_code=409, detail=NOT_WAITING) from exc
    try:
        store.discard(path)
    except ValueError:
        # The row is gone, and a path outside staging must never be deleted. Say so.
        log.warning("discarded upload pointed outside staging: %s", path)
    return StatusOut(status="discarded")


@router.post("/scholars", dependencies=Mutating)
def add_scholar(body: ScholarIn, config: Config, admin: Admin) -> ScholarOut:
    try:
        config.desk.add_scholar(body.id, body.name_ar, body.name_en, admin.email)
    except ScholarExists as exc:
        raise HTTPException(status_code=409, detail=SCHOLAR_EXISTS) from exc
    return ScholarOut(id=body.id, name_ar=body.name_ar, name_en=body.name_en)


__all__ = ["AdminConfig", "router", "safe_return"]
