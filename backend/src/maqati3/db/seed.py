"""Load `reference/` -- scholars and topics -- into the database.

The reference files are master data (CLAUDE.md, "Repo Layout"): ids are permanent, so
seeding inserts and updates names, and never deletes. `content_class` is never touched
on an existing topic: which topics stay out of the index is a human decision recorded
in the database, and a re-seed from a file that does not carry the field must not
silently reopen an excluded topic.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from maqati3.db.sql import Executor


@dataclass(frozen=True, slots=True)
class ScholarSeed:
    id: str
    name_ar: str
    name_en: str
    is_person: bool
    died_h: int | None
    died_ce: int | None
    note: str | None


@dataclass(frozen=True, slots=True)
class TopicSeed:
    id: str
    parent_id: str | None
    name_ar: str
    name_en: str


def _int_or_none(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


def load_scholars(path: Path) -> list[ScholarSeed]:
    """Parse scholars.csv. Lines starting with '#' are comments (the file opens with a
    DRAFT warning that is not a row)."""
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if not line.lstrip().startswith("#")]
    return [
        ScholarSeed(
            id=row["id"].strip(),
            name_ar=row["name_ar"].strip(),
            name_en=row["name_en"].strip(),
            is_person=row["type"].strip() != "body",
            died_h=_int_or_none(row.get("died_h")),
            died_ce=_int_or_none(row.get("died_ce")),
            note=(row.get("note") or "").strip() or None,
        )
        for row in csv.DictReader(lines)
        if row.get("id", "").strip()
    ]


def load_topics(path: Path) -> list[TopicSeed]:
    """Parse topics.yml into flat rows: each main topic, then its sub-topics as
    '<main>.<sub>' with the main topic as parent -- the id shape migration 0001 uses."""
    tree = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    topics: list[TopicSeed] = []
    for main_id, main in tree.items():
        topics.append(
            TopicSeed(id=main_id, parent_id=None, name_ar=main["name_ar"], name_en=main["name_en"])
        )
        for sub_id, sub in (main.get("sub") or {}).items():
            topics.append(
                TopicSeed(
                    id=f"{main_id}.{sub_id}",
                    parent_id=main_id,
                    name_ar=sub["ar"],
                    name_en=sub["en"],
                )
            )
    return topics


_UPSERT_SCHOLAR = """
INSERT INTO scholar (id, name_ar, name_en, is_person, died_h, died_ce, note)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    name_ar = EXCLUDED.name_ar, name_en = EXCLUDED.name_en, is_person = EXCLUDED.is_person,
    died_h = EXCLUDED.died_h, died_ce = EXCLUDED.died_ce, note = EXCLUDED.note
"""

# content_class is deliberately absent from the update: see the module docstring.
_UPSERT_TOPIC = """
INSERT INTO topic (id, parent_id, name_ar, name_en)
VALUES (%s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    parent_id = EXCLUDED.parent_id, name_ar = EXCLUDED.name_ar, name_en = EXCLUDED.name_en
"""


def seed_reference(
    executor: Executor, scholars: Sequence[ScholarSeed], topics: Sequence[TopicSeed]
) -> None:
    """Insert or update every scholar and topic, in one transaction."""
    with executor.transaction():
        for s in scholars:
            executor.execute(
                _UPSERT_SCHOLAR,
                (s.id, s.name_ar, s.name_en, s.is_person, s.died_h, s.died_ce, s.note),
            )
        # Parents before children, so the self-reference holds at every insert.
        for t in sorted(topics, key=lambda t: t.parent_id is not None):
            executor.execute(_UPSERT_TOPIC, (t.id, t.parent_id, t.name_ar, t.name_en))


__all__ = ["ScholarSeed", "TopicSeed", "load_scholars", "load_topics", "seed_reference"]
