"""Dedup layer 2: a byte-identical duplicate.

Exact and free -- computed before any extraction or ASR touches the file, so it can run
synchronously on a bulk upload and reject on the spot. No candidate shown, no decision
asked: the same bytes once already mean the same submission, so there is nothing for a
contributor to judge.
"""

from pathlib import Path

from maqati3.dedup.exact import find_exact_duplicate, sha256_hex, sha256_of_file


def test_sha256_hex_is_the_standard_hex_digest() -> None:
    # Known vector: sha256("") is this exact digest.
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_hex_differs_for_different_bytes() -> None:
    assert sha256_hex(b"first clip") != sha256_hex(b"second clip")


def test_sha256_hex_is_stable_across_calls() -> None:
    data = b"the same file, uploaded twice"
    assert sha256_hex(data) == sha256_hex(data)


def test_find_exact_duplicate_returns_none_for_an_unknown_digest() -> None:
    assert find_exact_duplicate("deadbeef", known={}) is None


def test_find_exact_duplicate_returns_the_existing_entry_id() -> None:
    known = {"deadbeef": "uthaymin-000421"}
    assert find_exact_duplicate("deadbeef", known=known) == "uthaymin-000421"


def test_find_exact_duplicate_is_case_sensitive_on_the_digest() -> None:
    # sha256_hex always lowercases; a caller handing in an uppercase digest from
    # elsewhere must not silently match -- that would hide a real bug upstream.
    known = {"deadbeef": "uthaymin-000421"}
    assert find_exact_duplicate("DEADBEEF", known=known) is None


# Uploaded files can be large (phone videos run to gigabytes); streaming the hash from
# disk is what keeps the check cheap enough to run synchronously on every upload.


def test_sha256_of_file_matches_sha256_of_its_bytes(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    data = b"a phone video, pretend bytes" * 1000
    path.write_bytes(data)
    assert sha256_of_file(path) == sha256_hex(data)


def test_sha256_of_file_reads_in_chunks_not_all_at_once(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    data = b"\x00" * 5000
    path.write_bytes(data)
    # chunk_size smaller than the file: correctness must not depend on reading it whole.
    assert sha256_of_file(path, chunk_size=64) == sha256_hex(data)
