"""Pending bulk uploads, and the Postgres side of dedup layers 2 and 3.

`PgKnownHashes` and `PgFingerprintIndex` implement the Protocols the upload route
triages against, over registered entries *and* pending submissions alike: one clip
saved by several brothers is uploaded several times before anyone registers the first
copy, so checking entries alone would let every copy through.

Layer 3's storage is migration 0003: one fingerprint per recording, plus a value-
sampled subset of its items as lookup keys (see `dedup.fingerprint.index_keys`).

The two kinds of match share one string namespace. An entry is its own id
('uthaymin-000421', which never contains a colon); a submission is
'submission:<sha256>'. Callers that need to tell them apart use `is_submission_key`.
"""

from __future__ import annotations

from collections.abc import Sequence, Set
from pathlib import Path

from psycopg import errors

from masdar.api.uploads import (
    SUBMISSION_PREFIX,
    InvalidMetadata,
    SubmissionMetadata,
    is_submission_key,
    submission_key,
)
from masdar.db.sql import Executor
from masdar.dedup.fingerprint import (
    ALGORITHM,
    MIN_SHARED_KEYS,
    Fingerprint,
    decode_items,
    encode_items,
    index_keys,
)

# A registered submission is no longer pending: its entry carries the hash and the
# windows from then on, and counting both would report one recording as two matches.
_PENDING = "state <> 'registered'"

_KNOWN_HASHES = f"""
SELECT sha256, %s || sha256 FROM submission WHERE {_PENDING}
UNION ALL
SELECT sha256, id FROM entry WHERE sha256 IS NOT NULL
"""

#: The most owners one upload is compared against in full. Past a handful the
#: contributor could not listen to them all anyway; the strongest come first.
MAX_CANDIDATES = 20

_CANDIDATES = f"""
SELECT owner FROM (
    SELECT entry_id AS owner FROM entry_fingerprint_key WHERE key = ANY(%s::bigint[])
    UNION ALL
    SELECT %s || k.sha256
      FROM submission_fingerprint_key k JOIN submission s USING (sha256)
     WHERE k.key = ANY(%s::bigint[]) AND s.{_PENDING}
) shared
GROUP BY owner
HAVING count(*) >= %s
ORDER BY count(*) DESC, owner
LIMIT %s
"""

_ENTRY_ITEMS = "SELECT items FROM entry_fingerprint WHERE entry_id = %s"
_SUBMISSION_ITEMS = "SELECT items FROM submission_fingerprint WHERE sha256 = %s"

_RECORD = """
INSERT INTO submission (sha256, original_name, staged_path, duration_ms, candidate_keys)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (sha256) DO NOTHING
RETURNING sha256
"""

_RECORD_ITEMS = (
    "INSERT INTO submission_fingerprint (sha256, algorithm, items) VALUES (%s, %s, %s)"
)

_RECORD_KEYS = (
    "INSERT INTO submission_fingerprint_key (key, sha256) "
    "SELECT unnest(%s::bigint[]), %s"
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

    def candidates(self, keys: Set[int]) -> set[str]:
        wanted = sorted(keys)
        rows = self._executor.fetchall(
            _CANDIDATES, (wanted, SUBMISSION_PREFIX, wanted, MIN_SHARED_KEYS, MAX_CANDIDATES)
        )
        return {str(row[0]) for row in rows}

    def items_of(self, key: str) -> Sequence[int]:
        if is_submission_key(key):
            rows = self._executor.fetchall(
                _SUBMISSION_ITEMS, (key.removeprefix(SUBMISSION_PREFIX),)
            )
        else:
            rows = self._executor.fetchall(_ENTRY_ITEMS, (key,))
        if not rows:
            return ()
        stored = rows[0][0]
        assert isinstance(stored, bytes | memoryview)
        return decode_items(bytes(stored))


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
        fingerprint: Fingerprint,
        candidate_keys: Sequence[str],
    ) -> bool:
        """Store a triaged upload. False if the same bytes were recorded first.

        That is the race between two brothers uploading one clip at the same moment:
        both pass the known-hashes check, and the primary key decides who was first.
        """
        with self._executor.transaction():
            won = self._executor.fetchall(
                _RECORD,
                (
                    sha256,
                    original_name,
                    str(staged_path),
                    fingerprint.duration_ms,
                    list(candidate_keys),
                ),
            )
            if not won:
                return False
            if fingerprint.items:
                self._executor.execute(
                    _RECORD_ITEMS, (sha256, ALGORITHM, encode_items(fingerprint.items))
                )
                self._executor.execute(
                    _RECORD_KEYS, (sorted(index_keys(fingerprint.items)), sha256)
                )
        return True

    def keep(self, sha256: str, metadata: SubmissionMetadata) -> bool:
        """Send a pending upload in. False if it was already decided, or never existed."""
        try:
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
        except errors.ForeignKeyViolation as exc:
            raise InvalidMetadata("unknown scholar or topic id") from exc
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
