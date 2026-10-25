"""Where an upload waits on disk while it is triaged and decided on.

Real filesystem in a temporary directory -- the disk is the behaviour under test here,
not a boundary to fake.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from masdar.api.uploads import UploadTooLarge
from masdar.dedup.exact import sha256_hex
from masdar.staging import LocalUploadStore

VIDEO = b"pretend phone video bytes" * 1000


def test_staging_writes_the_bytes_and_returns_their_hash(tmp_path: Path) -> None:
    staged = LocalUploadStore(tmp_path).stage("clip.mp4", io.BytesIO(VIDEO))

    assert staged.path.read_bytes() == VIDEO
    assert staged.sha256 == sha256_hex(VIDEO)


def test_the_staged_name_never_comes_from_the_client(tmp_path: Path) -> None:
    # A filename is whatever the client sends. Only a cleaned extension survives.
    staged = LocalUploadStore(tmp_path).stage("../../etc/passwd.MP4", io.BytesIO(VIDEO))

    assert staged.path.parent == tmp_path
    assert staged.path.suffix == ".mp4"
    assert "passwd" not in staged.path.name


@pytest.mark.parametrize("name", ["clip", "clip.", "clip.m p4", "clip.verylongextension", ""])
def test_an_unusable_extension_is_dropped(tmp_path: Path, name: str) -> None:
    staged = LocalUploadStore(tmp_path).stage(name, io.BytesIO(VIDEO))

    assert staged.path.suffix == ""


def test_two_uploads_with_the_same_name_do_not_collide(tmp_path: Path) -> None:
    store = LocalUploadStore(tmp_path)

    first = store.stage("clip.mp4", io.BytesIO(VIDEO))
    second = store.stage("clip.mp4", io.BytesIO(VIDEO + b"!"))

    assert first.path != second.path
    assert first.path.read_bytes() == VIDEO


def test_an_upload_past_the_limit_is_refused_and_leaves_nothing_behind(tmp_path: Path) -> None:
    store = LocalUploadStore(tmp_path, max_bytes=len(VIDEO) - 1)

    with pytest.raises(UploadTooLarge):
        store.stage("clip.mp4", io.BytesIO(VIDEO))

    assert list(tmp_path.iterdir()) == []


def test_an_upload_exactly_at_the_limit_is_accepted(tmp_path: Path) -> None:
    staged = LocalUploadStore(tmp_path, max_bytes=len(VIDEO)).stage("c.mp4", io.BytesIO(VIDEO))

    assert staged.path.stat().st_size == len(VIDEO)


def test_discarding_removes_the_file_and_tolerates_a_second_call(tmp_path: Path) -> None:
    store = LocalUploadStore(tmp_path)
    staged = store.stage("clip.mp4", io.BytesIO(VIDEO))

    store.discard(staged.path)
    store.discard(staged.path)

    assert not staged.path.exists()


def test_discard_refuses_anything_outside_the_staging_directory(tmp_path: Path) -> None:
    outside = tmp_path / "keep.txt"
    outside.write_text("not a staged upload")
    store = LocalUploadStore(tmp_path / "staging")

    with pytest.raises(ValueError, match="outside"):
        store.discard(outside)

    assert outside.exists()


def test_the_staging_directory_is_created_if_missing(tmp_path: Path) -> None:
    staged = LocalUploadStore(tmp_path / "a" / "b").stage("clip.mp4", io.BytesIO(VIDEO))

    assert staged.path.exists()
