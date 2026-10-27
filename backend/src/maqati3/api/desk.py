"""What an admin may do with uploads, as the dashboard's routes see it.

Types, errors and the two Protocols the admin routes are written against -- the same
split as `api/repository.py` and `api/uploads.py`. The Postgres implementations live in
`db/admin.py`; the routes are tested against fakes, the database against Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


class NotWaiting(LookupError):
    """The upload is not waiting for an admin: unknown, undecided, or already registered."""


class UnknownScholar(LookupError):
    """Registration named a scholar the archive does not have."""


class ScholarExists(ValueError):
    """A scholar with that id is already in the archive."""


@dataclass(frozen=True, slots=True)
class AdminUser:
    email: str
    name: str | None


@dataclass(frozen=True, slots=True)
class LogRecord:
    at: datetime
    admin_email: str
    action: str
    subject: str | None
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RegisteredAs:
    """The entry an upload became."""

    entry_id: str
    scholar_id: str
    scholar_name_ar: str
    scholar_name_en: str


@dataclass(frozen=True, slots=True)
class DashboardItem:
    """One upload as an admin sees it."""

    sha256: str
    original_name: str
    duration_ms: int
    received_at: datetime
    contributor: str | None
    #: Matches the contributor heard and kept the upload despite, in words: an entry by
    #: its id, another pending upload by its file and sender.
    kept_despite: list[str]
    entry: RegisteredAs | None
    registered_by: str | None


class Admins(Protocol):
    """The list of people allowed in, and the log of what they did."""

    def find(self, email: str) -> AdminUser | None: ...

    def add(self, email: str, *, name: str | None, added_by: str) -> bool:
        """Put an address on the list. False if it already was."""
        ...

    def remove(self, email: str) -> bool: ...

    def all(self) -> list[AdminUser]: ...

    def log(
        self, admin_email: str, action: str, subject: str | None, detail: dict[str, Any]
    ) -> None: ...

    def recent_log(self, *, limit: int) -> list[LogRecord]: ...


class Desk(Protocol):
    """The admin's work on uploads. Every change is logged with who made it."""

    def items(self) -> list[DashboardItem]:
        """Uploads waiting for an admin, oldest first, then registered ones, newest first."""
        ...

    def media_path(self, sha256: str) -> Path | None:
        """Where a kept or registered upload's file was staged, else None."""
        ...

    def register(self, sha256: str, scholar_id: str, admin_email: str) -> str:
        """Turn a waiting upload into a draft entry of ``scholar_id``; its entry id.

        The entry starts `not_sure` and `draft`: nothing about it is public until a human
        has set the attribution and approved the Arabic. Raises `NotWaiting` or
        `UnknownScholar`, and in either case creates nothing.
        """
        ...

    def discard(self, sha256: str, admin_email: str) -> Path:
        """Remove a waiting upload for good; its staged file, for the caller to delete.

        Raises `NotWaiting`. A registered upload cannot be discarded: it is an entry.
        """
        ...

    def add_scholar(
        self, scholar_id: str, name_ar: str, name_en: str, admin_email: str
    ) -> None:
        """Raises `ScholarExists`."""
        ...


__all__ = [
    "AdminUser",
    "Admins",
    "DashboardItem",
    "Desk",
    "LogRecord",
    "NotWaiting",
    "RegisteredAs",
    "ScholarExists",
    "UnknownScholar",
]
