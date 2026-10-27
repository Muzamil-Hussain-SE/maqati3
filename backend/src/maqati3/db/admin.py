"""The admin list, the audit log, and an admin's work on uploads, in Postgres.

Registering is the one multi-step write here: the entry, its three language rows, a copy
of the upload's fingerprint, and the upload's own state change all happen in one
transaction, so there is never an entry without its fingerprint, or an upload marked
registered that has no entry.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from maqati3.api.desk import (
    AdminUser,
    DashboardItem,
    LogRecord,
    NotWaiting,
    RegisteredAs,
    ScholarExists,
    UnknownScholar,
)
from maqati3.api.uploads import SUBMISSION_PREFIX, is_submission_key
from maqati3.db.sql import Executor

# ------------------------------------------------------------------ the admin list

_FIND = "SELECT email, name FROM admin WHERE email = %s"
_ADD = """
INSERT INTO admin (email, name, added_by) VALUES (%s, %s, %s)
ON CONFLICT (email) DO NOTHING RETURNING email
"""
_REMOVE = "DELETE FROM admin WHERE email = %s RETURNING email"
_ALL = "SELECT email, name FROM admin ORDER BY added_at, email"
_LOG = "INSERT INTO admin_log (admin_email, action, subject, detail) VALUES (%s, %s, %s, %s::jsonb)"
_RECENT = """
SELECT at, admin_email, action, subject, detail FROM admin_log ORDER BY at DESC, id DESC LIMIT %s
"""


def normalise(email: str) -> str:
    return email.strip().lower()


class PgAdmins:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def find(self, email: str) -> AdminUser | None:
        rows = self._executor.fetchall(_FIND, (normalise(email),))
        return AdminUser(email=str(rows[0][0]), name=_text(rows[0][1])) if rows else None

    def add(self, email: str, *, name: str | None, added_by: str) -> bool:
        return bool(self._executor.fetchall(_ADD, (normalise(email), name, added_by)))

    def remove(self, email: str) -> bool:
        return bool(self._executor.fetchall(_REMOVE, (normalise(email),)))

    def all(self) -> list[AdminUser]:
        return [AdminUser(email=str(e), name=_text(n)) for e, n in self._executor.fetchall(_ALL)]

    def log(
        self, admin_email: str, action: str, subject: str | None, detail: dict[str, Any]
    ) -> None:
        self._executor.execute(_LOG, (admin_email, action, subject, json.dumps(detail)))

    def recent_log(self, *, limit: int) -> list[LogRecord]:
        return [
            LogRecord(
                at=at if isinstance(at, datetime) else datetime.min,
                admin_email=str(email),
                action=str(action),
                subject=_text(subject),
                detail=detail if isinstance(detail, dict) else {},
            )
            for at, email, action, subject, detail in self._executor.fetchall(_RECENT, (limit,))
        ]


# ------------------------------------------------------------------ the desk

_ITEMS = """
SELECT s.sha256, s.original_name, s.duration_ms, s.received_at, s.contributor,
       s.candidate_keys, s.entry_id, s.registered_by,
       sc.id, sc.name_ar, sc.name_en
  FROM submission s
  LEFT JOIN entry e ON e.id = s.entry_id
  LEFT JOIN scholar sc ON sc.id = e.scholar_id
 WHERE s.state IN ('kept', 'registered')
 ORDER BY (s.state = 'registered'),
          CASE WHEN s.state = 'kept' THEN s.received_at END ASC,
          CASE WHEN s.state = 'registered' THEN s.registered_at END DESC,
          s.sha256
"""
_DESCRIBE_SUBMISSIONS = """
SELECT sha256, original_name, contributor FROM submission WHERE sha256 = ANY(%s)
"""
_MEDIA = "SELECT staged_path FROM submission WHERE sha256 = %s AND state IN ('kept', 'registered')"

_LOCK_WAITING = """
SELECT duration_ms, contributor FROM submission
 WHERE sha256 = %s AND state = 'kept' FOR UPDATE
"""
_SCHOLAR = "SELECT 1 FROM scholar WHERE id = %s"
_NEXT_NUMBER = "SELECT nextval('entry_number_seq')"
# attribution and visibility are left to their column defaults, 'not_sure' and 'draft':
# an admin choosing the scholar is a claim about whose words these are, not the
# established attribution that publishing requires.
_NEW_ENTRY = """
INSERT INTO entry (id, scholar_id, sha256, duration_sec, submitted_by)
VALUES (%s, %s, %s, %s, %s)
"""
_NEW_LANGUAGES = (
    "INSERT INTO entry_language (entry_id, lang) SELECT %s, unnest(enum_range(NULL::lang))"
)
_COPY_FINGERPRINT = """
INSERT INTO entry_fingerprint (entry_id, algorithm, items)
SELECT %s, algorithm, items FROM submission_fingerprint WHERE sha256 = %s
"""
_COPY_KEYS = """
INSERT INTO entry_fingerprint_key (key, entry_id)
SELECT key, %s FROM submission_fingerprint_key WHERE sha256 = %s
"""
_MARK_REGISTERED = """
UPDATE submission
   SET state = 'registered', entry_id = %s, registered_by = %s, registered_at = now()
 WHERE sha256 = %s
"""
_DISCARD = """
DELETE FROM submission WHERE sha256 = %s AND state = 'kept'
RETURNING staged_path, original_name, contributor
"""
_ADD_SCHOLAR = """
INSERT INTO scholar (id, name_ar, name_en) VALUES (%s, %s, %s)
ON CONFLICT (id) DO NOTHING RETURNING id
"""


def _text(value: object) -> str | None:
    return None if value is None else str(value)


class PgDesk:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor
        self._admins = PgAdmins(executor)

    def items(self) -> list[DashboardItem]:
        rows = self._executor.fetchall(_ITEMS)
        descriptions = self._describe(
            [key for row in rows for key in _keys(row[5])]
        )
        items = []
        for row in rows:
            entry_id = _text(row[6])
            items.append(
                DashboardItem(
                    sha256=str(row[0]),
                    original_name=str(row[1]),
                    duration_ms=int(str(row[2])),
                    received_at=row[3] if isinstance(row[3], datetime) else datetime.min,
                    contributor=_text(row[4]),
                    kept_despite=[descriptions.get(key, key) for key in _keys(row[5])],
                    entry=(
                        RegisteredAs(
                            entry_id=entry_id,
                            scholar_id=str(row[8]),
                            scholar_name_ar=str(row[9]),
                            scholar_name_en=str(row[10]),
                        )
                        if entry_id is not None
                        else None
                    ),
                    registered_by=_text(row[7]),
                )
            )
        return items

    def _describe(self, keys: list[str]) -> dict[str, str]:
        """Words for the matches an upload was kept despite. An entry is its id; another
        pending upload is its file and sender, because its hash tells an admin nothing."""
        wanted = [k.removeprefix(SUBMISSION_PREFIX) for k in keys if is_submission_key(k)]
        if not wanted:
            return {}
        return {
            SUBMISSION_PREFIX + str(sha): f"{name} ({sender})" if sender else str(name)
            for sha, name, sender in self._executor.fetchall(_DESCRIBE_SUBMISSIONS, (wanted,))
        }

    def media_path(self, sha256: str) -> Path | None:
        rows = self._executor.fetchall(_MEDIA, (sha256,))
        return Path(str(rows[0][0])) if rows else None

    def register(self, sha256: str, scholar_id: str, admin_email: str) -> str:
        with self._executor.transaction():
            waiting = self._executor.fetchall(_LOCK_WAITING, (sha256,))
            if not waiting:
                raise NotWaiting(sha256)
            if not self._executor.fetchall(_SCHOLAR, (scholar_id,)):
                raise UnknownScholar(scholar_id)
            duration_ms, contributor = waiting[0]
            number = int(str(self._executor.fetchall(_NEXT_NUMBER)[0][0]))
            entry_id = f"{scholar_id}-{number:06d}"
            self._executor.execute(
                _NEW_ENTRY,
                (entry_id, scholar_id, sha256, round(int(str(duration_ms)) / 1000), contributor),
            )
            self._executor.execute(_NEW_LANGUAGES, (entry_id,))
            self._executor.execute(_COPY_FINGERPRINT, (entry_id, sha256))
            self._executor.execute(_COPY_KEYS, (entry_id, sha256))
            self._executor.execute(_MARK_REGISTERED, (entry_id, admin_email, sha256))
            self._admins.log(
                admin_email, "register", sha256, {"entry_id": entry_id, "scholar_id": scholar_id}
            )
        return entry_id

    def discard(self, sha256: str, admin_email: str) -> Path:
        with self._executor.transaction():
            rows = self._executor.fetchall(_DISCARD, (sha256,))
            if not rows:
                raise NotWaiting(sha256)
            path, original_name, contributor = rows[0]
            self._admins.log(
                admin_email,
                "discard",
                sha256,
                {"original_name": str(original_name), "contributor": _text(contributor)},
            )
        return Path(str(path))

    def add_scholar(
        self, scholar_id: str, name_ar: str, name_en: str, admin_email: str
    ) -> None:
        with self._executor.transaction():
            if not self._executor.fetchall(_ADD_SCHOLAR, (scholar_id, name_ar, name_en)):
                raise ScholarExists(scholar_id)
            self._admins.log(admin_email, "add_scholar", scholar_id, {"name_en": name_en})


def _keys(value: object) -> list[str]:
    return [str(key) for key in value] if isinstance(value, list) else []


__all__ = ["PgAdmins", "PgDesk", "normalise"]
