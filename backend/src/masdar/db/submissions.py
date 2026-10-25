"""Pending bulk uploads, and the Postgres side of dedup layers 2 and 3.

`PgKnownHashes` and `PgFingerprintIndex` implement the Protocols the upload route
triages against, over registered entries *and* pending submissions alike: one clip
saved by several brothers is uploaded several times before anyone registers the first
copy, so checking entries alone would let every copy through.

The two kinds of match share one string namespace. An entry is its own id
('uthaymin-000421', which never contains a colon); a submission is
'submission:<sha256>'. Callers that need to tell them apart use `is_submission_key`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from masdar.db.sql import Executor
from masdar.dedup.fingerprint import WindowFingerprint
from masdar.domain import Attribution

SUBMISSION_PREFIX = "submission:"


def submission_key(sha256: str) -> str:
    return SUBMISSION_PREFIX + sha256


def is_submission_key(key: str) -> bool:
    return key.startswith(SUBMISSION_PREFIX)


@dataclass(frozen=True, slots=True)
class SubmissionMetadata:
    """What the contributor said about a kept upload. Claims, not facts."""

    contributor: str | None
    scholar_id: str | None
    scholar_other: str | None
    topic_id: str | None
    claimed_attribution: Attribution
    source_note: str | None
    note: str | None


# A registered submission is no longer pending: its entry carries the hash and the
# windows from then on, and counting both would report one recording as two matches.
_PENDING = "state <> 'registered'"

_KNOWN_HASHES = f"""
SELECT sha256, %s || sha256 FROM submission WHERE {_PENDING}
UNION ALL
SELECT sha256, id FROM entry WHERE sha256 IS NOT NULL
"""

_SHARING_A_WINDOW = f"""
SELECT DISTINCT entry_id FROM entry_fingerprint WHERE fingerprint = ANY(%s)
UNION
SELECT DISTINCT %s || f.sha256
  FROM submission_fingerprint f JOIN submission s USING (sha256)
 WHERE f.fingerprint = ANY(%s) AND s.{_PENDING}
"""

_ENTRY_WINDOWS = (
    "SELECT fingerprint FROM entry_fingerprint WHERE entry_id = %s ORDER BY window_idx"
)
_SUBMISSION_WINDOWS = (
    "SELECT fingerprint FROM submission_fingerprint WHERE sha256 = %s ORDER BY window_idx"
)

_RECORD = """
INSERT INTO submission (sha256, original_name, staged_path, duration_ms, candidate_keys)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (sha256) DO NOTHING
RETURNING sha256
"""

_RECORD_WINDOW = (
    "INSERT INTO submission_fingerprint (sha256, window_idx, offset_ms, fingerprint) "
    "VALUES (%s, %s, %s, %s)"
)

_KEEP = """
UPDATE submission
   SET state = 'kept', decided_at = now(),
       contributor = %s, scholar_id = %s, scholar_other = %s, topic_id = %s,
       claimed_attribution = %s, source_note = %s, note = %s
 WHERE sha256 = %s AND state = 'awaiting_decision'
RETURNING sha256
"""

_DROP = """
DELETE FROM submission
 WHERE sha256 = %s AND state = 'awaiting_decision'
RETURNING staged_path
"""


class PgKnownHashes:
    """`api.uploads.KnownHashes` over entries and pending submissions."""

    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def known(self) -> dict[str, str]:
        known: dict[str, str] = {}
        # Entries come second in the query, so an entry wins if a hash ever appears on
        # both sides: a match should point at what is registered, not at its upload.
        for sha256, key in self._executor.fetchall(_KNOWN_HASHES, (SUBMISSION_PREFIX,)):
            known[str(sha256)] = str(key)
        return known


class PgFingerprintIndex:
    """`dedup.triage.FingerprintIndex` over entries and pending submissions."""

    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def entries_sharing_a_window(self, fingerprints: Sequence[bytes]) -> set[str]:
        prints = list(fingerprints)
        rows = self._executor.fetchall(_SHARING_A_WINDOW, (prints, SUBMISSION_PREFIX, prints))
        return {str(row[0]) for row in rows}

    def windows_of(self, entry_id: str) -> Sequence[bytes]:
        if is_submission_key(entry_id):
            rows = self._executor.fetchall(
                _SUBMISSION_WINDOWS, (entry_id.removeprefix(SUBMISSION_PREFIX),)
            )
        else:
            rows = self._executor.fetchall(_ENTRY_WINDOWS, (entry_id,))
        return [bytes(row[0]) for row in rows]  # type: ignore[call-overload]


class PgSubmissions:
    """`api.uploads.Submissions`: record a triaged upload, then keep or drop it."""

    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def record(
        self,
        *,
        sha256: str,
        original_name: str,
        staged_path: Path,
        duration_ms: int,
        fingerprints: Sequence[WindowFingerprint],
        candidate_keys: Sequence[str],
    ) -> bool:
        """Store a triaged upload. False if the same bytes were recorded first.

        That is the race between two brothers uploading one clip at the same moment:
        both pass the known-hashes check, and the primary key decides who was first.
        """
        with self._executor.transaction():
            won = self._executor.fetchall(
                _RECORD,
                (sha256, original_name, str(staged_path), duration_ms, list(candidate_keys)),
            )
            if not won:
                return False
            for row in fingerprints:
                self._executor.execute(
                    _RECORD_WINDOW, (sha256, row.window_idx, row.offset_ms, row.fingerprint)
                )
        return True

    def keep(self, sha256: str, metadata: SubmissionMetadata) -> bool:
        """Send a pending upload in. False if it was already decided, or never existed."""
        rows = self._executor.fetchall(
            _KEEP,
            (
                metadata.contributor,
                metadata.scholar_id,
                metadata.scholar_other,
                metadata.topic_id,
                metadata.claimed_attribution.value,
                metadata.source_note,
                metadata.note,
                sha256,
            ),
        )
        return bool(rows)

    def drop(self, sha256: str) -> Path | None:
        """Delete a pending upload. Returns its staged file for the caller to remove, or
        None if there was nothing pending -- so a file is never deleted twice."""
        rows = self._executor.fetchall(_DROP, (sha256,))
        return Path(str(rows[0][0])) if rows else None


__all__ = [
    "SUBMISSION_PREFIX",
    "PgFingerprintIndex",
    "PgKnownHashes",
    "PgSubmissions",
    "SubmissionMetadata",
    "is_submission_key",
    "submission_key",
]
