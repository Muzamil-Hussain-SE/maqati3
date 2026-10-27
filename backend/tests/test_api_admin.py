"""The admin dashboard's routes: signing in, and what a signed-in admin may do.

Every way in that must stay shut has a test: no sign-in, a forged callback, an address
that is not on the list, an admin removed after signing in, an app with no login
configured. The provider (Google), the admin list and the desk are fakes of their
Protocols -- genuinely external or tested against Postgres elsewhere -- while the routes,
the session and the gates are the real thing.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from maqati3.api.admin import AdminConfig
from maqati3.api.app import create_app
from maqati3.api.desk import (
    AdminUser,
    DashboardItem,
    LogRecord,
    NotWaiting,
    RegisteredAs,
    ScholarExists,
    UnknownScholar,
)
from maqati3.api.uploads import StagedUpload
from maqati3.auth.identity import Identity, IdentityError

PUBLIC_URL = "https://archiv.example.org"
SECRET = "x" * 48
CSRF = {"X-Requested-With": "maqati3"}
NOW = datetime(2026, 10, 27, 14, 0, tzinfo=UTC)


class FakeProvider:
    """Google's stand-in: the code a callback carries says who signed in."""

    def __init__(self) -> None:
        self.redirect_uris: list[str] = []

    def authorization_url(self, *, redirect_uri: str, state: str, nonce: str) -> str:
        self.redirect_uris.append(redirect_uri)
        return f"https://accounts.example/auth?state={state}&nonce={nonce}"

    def identify(self, *, code: str, redirect_uri: str, nonce: str) -> Identity:
        if code == "forged":
            raise IdentityError("the token was forged")
        email = code.removeprefix("code-for:")
        return Identity(email=email.lower(), email_verified=True, name=email.split("@")[0].title())


class FakeAdmins:
    def __init__(self, *emails: str) -> None:
        self.admins = {e: AdminUser(e, e.split("@")[0].title()) for e in emails}
        self.logged: list[tuple[str, str, str | None, dict[str, Any]]] = []

    def find(self, email: str) -> AdminUser | None:
        return self.admins.get(email.strip().lower())

    def add(self, email: str, *, name: str | None, added_by: str) -> bool:
        return False

    def remove(self, email: str) -> bool:
        return self.admins.pop(email, None) is not None

    def all(self) -> list[AdminUser]:
        return list(self.admins.values())

    def log(
        self, admin_email: str, action: str, subject: str | None, detail: dict[str, Any]
    ) -> None:
        self.logged.append((admin_email, action, subject, detail))

    def recent_log(self, *, limit: int) -> list[LogRecord]:
        return []


WAITING = DashboardItem(
    sha256="aaa",
    original_name="clip.mp4",
    duration_ms=80_333,
    received_at=NOW,
    contributor="Abdullah",
    kept_despite=["ibn-baz-000007"],
    entry=None,
    registered_by=None,
)
REGISTERED = replace(
    WAITING,
    sha256="bbb",
    original_name="done.mp4",
    kept_despite=[],
    entry=RegisteredAs("ibn-baz-000001", "ibn-baz", "ابن باز", "Ibn Baz"),
    registered_by="yusuf@example.org",
)


class FakeDesk:
    def __init__(self) -> None:
        self.waiting = {"aaa": WAITING}
        self.registered = {"bbb": REGISTERED}
        self.calls: list[tuple[Any, ...]] = []
        self.scholars = {"ibn-baz"}

    def items(self) -> list[DashboardItem]:
        return [*self.waiting.values(), *self.registered.values()]

    def media_path(self, sha256: str) -> Path | None:
        known = {**self.waiting, **self.registered}
        return Path(f"/staging/{sha256}.mp4") if sha256 in known else None

    def register(self, sha256: str, scholar_id: str, admin_email: str) -> str:
        if sha256 not in self.waiting:
            raise NotWaiting(sha256)
        if scholar_id not in self.scholars:
            raise UnknownScholar(scholar_id)
        self.calls.append(("register", sha256, scholar_id, admin_email))
        del self.waiting[sha256]
        return f"{scholar_id}-000042"

    def discard(self, sha256: str, admin_email: str) -> Path:
        if sha256 not in self.waiting:
            raise NotWaiting(sha256)
        self.calls.append(("discard", sha256, admin_email))
        del self.waiting[sha256]
        return Path(f"/staging/{sha256}.mp4")

    def add_scholar(self, scholar_id: str, name_ar: str, name_en: str, admin_email: str) -> None:
        if scholar_id in self.scholars:
            raise ScholarExists(scholar_id)
        self.calls.append(("add_scholar", scholar_id, name_ar, name_en, admin_email))
        self.scholars.add(scholar_id)


class FakeStore:
    def __init__(self, on_disk: dict[Path, Path] | None = None) -> None:
        self.on_disk = on_disk or {}
        self.discarded: list[Path] = []

    def stage(self, filename: str, stream: Any) -> StagedUpload:
        raise NotImplementedError

    def discard(self, path: Path) -> None:
        self.discarded.append(path)

    def locate(self, path: Path) -> Path | None:
        return self.on_disk.get(path)


class FakeRepository:
    def entry(self, entry_id: str) -> None:
        return None


class Setup:
    def __init__(
        self,
        *emails: str,
        with_admin: bool = True,
        store: FakeStore | None = None,
        secret: str = SECRET,
    ):
        self.provider = FakeProvider()
        self.admins = FakeAdmins(*(emails or ("yusuf@example.org",)))
        self.desk = FakeDesk()
        self.store = store or FakeStore()
        config = (
            AdminConfig(
                provider=self.provider,
                admins=self.admins,
                desk=self.desk,
                public_url=PUBLIC_URL,
                session_secret=secret,
            )
            if with_admin
            else None
        )
        app = create_app(FakeRepository(), store=self.store, admin=config)  # type: ignore[arg-type]
        self.client = TestClient(app, base_url="https://testserver")


def login(setup: Setup, email: str = "yusuf@example.org", **params: str) -> Response:
    start = setup.client.get("/api/v1/admin/auth/login", params=params, follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return setup.client.get(
        "/api/v1/admin/auth/callback",
        params={"code": f"code-for:{email}", "state": state},
        follow_redirects=False,
    )


def signed_in(*emails: str, store: FakeStore | None = None) -> Setup:
    setup = Setup(*emails, store=store)
    assert login(setup).status_code == 303
    return setup


# ------------------------------------------------------------------ signing in


def test_the_login_sends_the_browser_to_the_provider_with_our_callback() -> None:
    setup = Setup()

    response = setup.client.get("/api/v1/admin/auth/login", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("https://accounts.example/auth?")
    assert setup.provider.redirect_uris == [f"{PUBLIC_URL}/api/v1/admin/auth/callback"]


def test_an_admin_on_the_list_is_signed_in_and_sent_on() -> None:
    setup = Setup()

    response = login(setup)

    assert response.status_code == 303
    assert response.headers["location"] == "/en/admin"
    me = setup.client.get("/api/v1/admin/me")
    assert me.status_code == 200
    assert me.json() == {"email": "yusuf@example.org", "name": "Yusuf"}


def test_the_page_the_admin_came_from_is_where_they_land() -> None:
    setup = Setup()

    response = login(setup, **{"return": "/de/admin"})

    assert response.headers["location"] == "/de/admin"


@pytest.mark.parametrize(
    "bad",
    ["https://evil.example/steal", "//evil.example", "/\\evil.example", "javascript:alert(1)", ""],
)
def test_a_login_cannot_be_used_to_redirect_elsewhere(bad: str) -> None:
    setup = Setup()

    response = login(setup, **{"return": bad})

    assert response.headers["location"] == "/en/admin"


def test_an_address_that_is_not_on_the_list_does_not_get_in() -> None:
    setup = Setup("yusuf@example.org")

    response = login(setup, "stranger@example.org")

    assert response.status_code == 303
    assert response.headers["location"] == "/en/admin?login=denied"
    assert setup.client.get("/api/v1/admin/me").status_code == 401
    # Who tried is worth knowing.
    assert setup.admins.logged == [("stranger@example.org", "login_denied", None, {})]


def test_the_address_is_matched_whatever_its_case() -> None:
    setup = Setup("yusuf@example.org")

    login(setup, "Yusuf@Example.ORG")

    assert setup.client.get("/api/v1/admin/me").status_code == 200


def test_a_callback_with_the_wrong_state_is_refused() -> None:
    setup = Setup()
    setup.client.get("/api/v1/admin/auth/login", follow_redirects=False)

    response = setup.client.get(
        "/api/v1/admin/auth/callback",
        params={"code": "code-for:yusuf@example.org", "state": "someone-elses"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert setup.client.get("/api/v1/admin/me").status_code == 401


def test_a_callback_without_a_login_started_in_this_browser_is_refused() -> None:
    setup = Setup()

    response = setup.client.get(
        "/api/v1/admin/auth/callback",
        params={"code": "code-for:yusuf@example.org", "state": "anything"},
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_a_callback_cannot_be_replayed() -> None:
    setup = Setup()
    start = setup.client.get("/api/v1/admin/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    params = {"code": "code-for:yusuf@example.org", "state": state}
    first = setup.client.get("/api/v1/admin/auth/callback", params=params, follow_redirects=False)
    assert first.status_code == 303
    setup.client.post("/api/v1/admin/auth/logout", headers=CSRF)

    again = setup.client.get("/api/v1/admin/auth/callback", params=params, follow_redirects=False)

    assert again.status_code == 400
    assert setup.client.get("/api/v1/admin/me").status_code == 401


def test_a_token_the_provider_refuses_is_a_failed_login_not_a_crash() -> None:
    setup = Setup()
    start = setup.client.get("/api/v1/admin/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    response = setup.client.get(
        "/api/v1/admin/auth/callback",
        params={"code": "forged", "state": state},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/en/admin?login=failed"
    assert setup.client.get("/api/v1/admin/me").status_code == 401


def test_the_provider_reporting_an_error_is_a_failed_login() -> None:
    setup = Setup()
    start = setup.client.get("/api/v1/admin/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    response = setup.client.get(
        "/api/v1/admin/auth/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/en/admin?login=failed"


def test_signing_in_is_written_to_the_log() -> None:
    setup = signed_in()

    assert setup.admins.logged == [("yusuf@example.org", "login", None, {})]


def test_signing_out_ends_the_session() -> None:
    setup = signed_in()

    response = setup.client.post("/api/v1/admin/auth/logout", headers=CSRF)

    assert response.status_code == 200
    assert setup.client.get("/api/v1/admin/me").status_code == 401


def test_an_admin_removed_from_the_list_is_locked_out_at_once() -> None:
    # The list is checked on every request, not only at sign-in.
    setup = signed_in()
    assert setup.client.get("/api/v1/admin/me").status_code == 200

    setup.admins.remove("yusuf@example.org")

    assert setup.client.get("/api/v1/admin/me").status_code == 401
    assert setup.client.get("/api/v1/admin/submissions").status_code == 401


def test_the_session_cookie_cannot_be_read_by_scripts_and_only_travels_over_https() -> None:
    setup = Setup()

    response = login(setup)

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie


def test_a_session_signed_with_another_secret_is_not_a_session() -> None:
    elsewhere = Setup(secret="y" * 48)
    assert login(elsewhere).status_code == 303
    cookie = elsewhere.client.cookies.get("maqati3_admin")
    assert cookie is not None

    setup = Setup()
    setup.client.cookies.set("maqati3_admin", cookie)

    assert setup.client.get("/api/v1/admin/me").status_code == 401


def test_a_tampered_session_cookie_is_not_a_session() -> None:
    setup = signed_in()
    cookie = setup.client.cookies.get("maqati3_admin")
    assert cookie is not None

    setup.client.cookies.set("maqati3_admin", cookie[:-4] + "AAAA")

    assert setup.client.get("/api/v1/admin/me").status_code == 401


# ------------------------------------------------------------------ fail closed


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/auth/login"),
        ("get", "/api/v1/admin/me"),
        ("get", "/api/v1/admin/submissions"),
        ("get", "/api/v1/admin/submissions/aaa/media"),
        ("post", "/api/v1/admin/submissions/aaa/register"),
        ("post", "/api/v1/admin/submissions/aaa/discard"),
        ("post", "/api/v1/admin/scholars"),
    ],
)
def test_an_app_without_a_login_configured_serves_no_admin_route(method: str, path: str) -> None:
    setup = Setup(with_admin=False)

    response = getattr(setup.client, method)(path, headers=CSRF, follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"] == "admin_not_configured"


def test_a_session_secret_that_is_too_short_refuses_to_build_the_app() -> None:
    config = AdminConfig(
        provider=FakeProvider(),
        admins=FakeAdmins(),
        desk=FakeDesk(),
        public_url=PUBLIC_URL,
        session_secret="short",
    )

    with pytest.raises(ValueError, match="session secret"):
        create_app(FakeRepository(), admin=config)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/me"),
        ("get", "/api/v1/admin/submissions"),
        ("get", "/api/v1/admin/submissions/aaa/media"),
        ("post", "/api/v1/admin/submissions/aaa/register"),
        ("post", "/api/v1/admin/submissions/aaa/discard"),
        ("post", "/api/v1/admin/scholars"),
    ],
)
def test_nobody_signed_in_reaches_an_admin_route(method: str, path: str) -> None:
    setup = Setup()

    response = getattr(setup.client, method)(path, headers=CSRF)

    assert response.status_code == 401
    assert response.json()["detail"] == "admin_login_required"


def test_the_upload_key_is_not_an_admin_credential() -> None:
    setup = Setup()

    response = setup.client.get("/api/v1/admin/submissions", headers={"X-Upload-Key": "anything"})

    assert response.status_code == 401


# ------------------------------------------------------------------ the dashboard


def test_the_dashboard_lists_what_waits_and_what_is_registered() -> None:
    setup = signed_in()

    body = setup.client.get("/api/v1/admin/submissions").json()

    assert [i["sha256"] for i in body] == ["aaa", "bbb"]
    waiting, registered = body
    assert waiting == {
        "sha256": "aaa",
        "original_name": "clip.mp4",
        "duration_ms": 80_333,
        "received_at": "2026-10-27T14:00:00Z",
        "contributor": "Abdullah",
        "kept_despite": ["ibn-baz-000007"],
        "status": "waiting",
        "entry": None,
        "registered_by": None,
    }
    assert registered["status"] == "registered"
    assert registered["entry"] == {
        "entry_id": "ibn-baz-000001",
        "scholar": {"id": "ibn-baz", "name_ar": "ابن باز", "name_en": "Ibn Baz"},
    }
    assert registered["registered_by"] == "yusuf@example.org"


def test_an_admin_can_play_an_upload(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video_bytes = b"the brother's clip" * 100
    video.write_bytes(video_bytes)
    setup = signed_in(store=FakeStore({Path("/staging/aaa.mp4"): video}))

    response = setup.client.get("/api/v1/admin/submissions/aaa/media")

    assert response.status_code == 200
    assert response.content == video_bytes
    assert response.headers["content-type"] == "video/mp4"


def test_playing_supports_seeking(tmp_path: Path) -> None:
    # Browsers fetch video in byte ranges; without them nothing past the start plays.
    video = tmp_path / "clip.mp4"
    video_bytes = b"0123456789" * 100
    video.write_bytes(video_bytes)
    setup = signed_in(store=FakeStore({Path("/staging/aaa.mp4"): video}))

    response = setup.client.get(
        "/api/v1/admin/submissions/aaa/media", headers={"Range": "bytes=10-19"}
    )

    assert response.status_code == 206
    assert response.content == video_bytes[10:20]


def test_media_of_something_unknown_or_missing_on_disk_is_not_found() -> None:
    setup = signed_in()  # the store vouches for nothing

    assert setup.client.get("/api/v1/admin/submissions/aaa/media").status_code == 404
    assert setup.client.get("/api/v1/admin/submissions/nothing/media").status_code == 404


# ------------------------------------------------------------------ registering


def test_registering_creates_the_entry_for_the_chosen_scholar() -> None:
    setup = signed_in()

    response = setup.client.post(
        "/api/v1/admin/submissions/aaa/register", json={"scholar_id": "ibn-baz"}, headers=CSRF
    )

    assert response.status_code == 200
    assert response.json() == {"entry_id": "ibn-baz-000042"}
    assert setup.desk.calls == [("register", "aaa", "ibn-baz", "yusuf@example.org")]


def test_registering_for_a_scholar_the_archive_does_not_have_is_refused() -> None:
    setup = signed_in()

    response = setup.client.post(
        "/api/v1/admin/submissions/aaa/register", json={"scholar_id": "nobody"}, headers=CSRF
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "unknown_scholar"


def test_registering_something_not_waiting_is_a_conflict() -> None:
    setup = signed_in()

    response = setup.client.post(
        "/api/v1/admin/submissions/bbb/register", json={"scholar_id": "ibn-baz"}, headers=CSRF
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "not_waiting"


def test_registering_needs_a_scholar() -> None:
    setup = signed_in()

    for body in ({}, {"scholar_id": ""}, {"scholar_id": "   "}):
        response = setup.client.post(
            "/api/v1/admin/submissions/aaa/register", json=body, headers=CSRF
        )
        assert response.status_code == 422

    assert setup.desk.calls == []


# ------------------------------------------------------------------ discarding


def test_discarding_removes_the_upload_and_its_file() -> None:
    store = FakeStore()
    setup = signed_in(store=store)

    response = setup.client.post("/api/v1/admin/submissions/aaa/discard", headers=CSRF)

    assert response.status_code == 200
    assert response.json() == {"status": "discarded"}
    assert setup.desk.calls == [("discard", "aaa", "yusuf@example.org")]
    assert store.discarded == [Path("/staging/aaa.mp4")]


def test_discarding_something_not_waiting_touches_no_file() -> None:
    store = FakeStore()
    setup = signed_in(store=store)

    response = setup.client.post("/api/v1/admin/submissions/bbb/discard", headers=CSRF)

    assert response.status_code == 409
    assert store.discarded == []


# ------------------------------------------------------------------ scholars


def test_an_admin_can_add_a_scholar() -> None:
    setup = signed_in()

    response = setup.client.post(
        "/api/v1/admin/scholars",
        json={"id": "rabi-al-madkhali", "name_ar": "ربيع المدخلي", "name_en": "Rabi al-Madkhali"},
        headers=CSRF,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "rabi-al-madkhali"}
    assert setup.desk.calls == [
        ("add_scholar", "rabi-al-madkhali", "ربيع المدخلي", "Rabi al-Madkhali", "yusuf@example.org")
    ]


@pytest.mark.parametrize(
    "bad_id", ["", "Has Spaces", "UPPER", "-leading", "trailing-", "a/b", "../x"]
)
def test_a_scholar_id_must_be_a_plain_slug(bad_id: str) -> None:
    # The id becomes the front of every entry id and ends up in URLs.
    setup = signed_in()

    response = setup.client.post(
        "/api/v1/admin/scholars",
        json={"id": bad_id, "name_ar": "ا", "name_en": "A"},
        headers=CSRF,
    )

    assert response.status_code == 422
    assert setup.desk.calls == []


def test_adding_a_scholar_that_exists_is_a_conflict() -> None:
    setup = signed_in()

    response = setup.client.post(
        "/api/v1/admin/scholars",
        json={"id": "ibn-baz", "name_ar": "ا", "name_en": "A"},
        headers=CSRF,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "scholar_exists"


# ------------------------------------------------------------------ forged requests


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/admin/submissions/aaa/register", {"scholar_id": "ibn-baz"}),
        ("/api/v1/admin/submissions/aaa/discard", None),
        ("/api/v1/admin/scholars", {"id": "x-y", "name_ar": "ا", "name_en": "A"}),
        ("/api/v1/admin/auth/logout", None),
    ],
)
def test_a_signed_in_admin_cannot_be_made_to_act_by_another_site(
    path: str, body: dict[str, str] | None
) -> None:
    # A cross-site form cannot set a custom header, so without it the request is not
    # the dashboard's own.
    setup = signed_in()

    response = setup.client.post(path, json=body)

    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_header_missing"
    assert setup.desk.calls == []
    assert setup.client.get("/api/v1/admin/me").status_code == 200


def test_the_public_site_sets_no_cookie_and_needs_no_session() -> None:
    setup = Setup()

    response = setup.client.get("/health")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers
