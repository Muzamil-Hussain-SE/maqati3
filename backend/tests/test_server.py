"""End to end: the real app over real Postgres, real fpcalc, a real staging directory.

The one test that exercises the wiring a deployment runs, through the sequence a
contributor actually goes through. Needs DATABASE_URL, fpcalc and ffmpeg.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from masdar.server import Settings, build_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL")
    or shutil.which("fpcalc") is None
    or shutil.which("ffmpeg") is None,
    reason="end-to-end test: needs DATABASE_URL, fpcalc and ffmpeg",
)

REPO = Path(__file__).resolve().parents[2]
SCHEMA = "masdar_e2e"
UPLOAD_KEY = "e2e-key"
KEYED = {"X-Upload-Key": UPLOAD_KEY}


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    import psycopg

    from masdar.db.migrate import migrate
    from masdar.db.seed import load_scholars, load_topics, seed_reference
    from masdar.db.sql import PsycopgExecutor

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        connection.execute(f"CREATE SCHEMA {SCHEMA}")
        connection.execute(f"SET search_path TO {SCHEMA}, public")
        executor = PsycopgExecutor(connection)
        migrate(executor, REPO / "db" / "migrations")
        seed_reference(
            executor,
            load_scholars(REPO / "reference" / "scholars.csv"),
            load_topics(REPO / "reference" / "topics.yml"),
        )
        settings = Settings(
            database_url=os.environ["DATABASE_URL"],
            staging_dir=tmp_path / "staging",
            upload_key=UPLOAD_KEY,
        )
        try:
            app = build_app(
                settings, connect_kwargs={"options": f"-c search_path={SCHEMA},public"}
            )
            with TestClient(app) as test_client:
                yield test_client
        finally:
            connection.execute("SET search_path TO public")
            connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


@pytest.fixture
def media(tmp_path: Path) -> dict[str, Path]:
    expr = "0.6*sin(2*PI*(220+150*sin(t*1.3))*t)+0.4*sin(2*PI*(660+300*sin(t*0.7))*t)"
    original = tmp_path / "fatwa.wav"
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':s=22050:d=60", str(original))
    forwarded = tmp_path / "forwarded.m4a"
    ffmpeg("-i", str(original), "-c:a", "aac", "-b:a", "64k", str(forwarded))
    garbage = tmp_path / "photo.mp4"
    garbage.write_bytes(b"\xff\xd8\xff\xe0 not a video")
    return {"original": original, "forwarded": forwarded, "garbage": garbage}


def upload(client: TestClient, path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        response = client.post(
            "/api/v1/uploads", files={"file": (path.name, handle)}, headers=KEYED
        )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_a_contributor_uploads_keeps_and_is_protected_from_duplicates(
    client: TestClient, media: dict[str, Path], tmp_path: Path
) -> None:
    # The dropdowns the page fills come from the seeded reference data.
    scholars = client.get("/api/v1/scholars").json()
    assert "ibn-uthaymin" in {s["id"] for s in scholars}
    assert any(t["id"] == "fiqh" for t in client.get("/api/v1/topics").json())

    # 1. A first upload is new, and is kept with what the contributor says about it.
    first = upload(client, media["original"])
    assert first["status"] == "new"
    kept = client.post(
        f"/api/v1/uploads/{first['sha256']}/decision",
        headers=KEYED,
        json={"keep": True, "contributor": "Abdullah"},
    )
    assert kept.json() == {"sha256": first["sha256"], "status": "kept"}

    # 2. The same file again -- another brother had it too -- is rejected outright.
    again = upload(client, media["original"])
    assert again["status"] == "rejected"
    assert again["duplicate_of"] == {
        "public": False, "pending": True, "preview_id": first["sha256"], "source_url": None,
        "entry_id": None, "scholar": None, "title_ar": None, "title_en": None,
        "duration_sec": None, "overlap_ms": None,
    }

    # The page can play the pending original for comparison -- with the link's key.
    preview = client.get(f"/api/v1/uploads/{first['sha256']}/media?k={UPLOAD_KEY}")
    assert preview.status_code == 200
    assert preview.content == media["original"].read_bytes()

    # 3. A forwarded, re-encoded copy is not byte-identical, so it becomes a candidate
    #    pointing at the pending upload -- and the contributor drops it.
    forwarded = upload(client, media["forwarded"])
    assert forwarded["status"] == "candidates"
    candidates = forwarded["candidates"]
    assert isinstance(candidates, list) and candidates[0]["pending"] is True
    dropped = client.post(
        f"/api/v1/uploads/{forwarded['sha256']}/decision", json={"keep": False}, headers=KEYED
    )
    assert dropped.json()["status"] == "dropped"

    # Only the kept original is left on disk.
    assert len(list((tmp_path / "staging").iterdir())) == 1


def test_a_file_without_audio_is_refused_and_not_kept(
    client: TestClient, media: dict[str, Path], tmp_path: Path
) -> None:
    with media["garbage"].open("rb") as handle:
        response = client.post(
            "/api/v1/uploads", files={"file": ("photo.mp4", handle)}, headers=KEYED
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "no_readable_audio"
    assert list((tmp_path / "staging").iterdir()) == []


def test_the_server_refuses_to_build_without_an_upload_key(tmp_path: Path) -> None:
    # Fail closed: a deployment that forgot the key must not serve an open upload API.
    with pytest.raises(ValueError, match="UPLOAD_KEY"):
        build_app(
            Settings(database_url="postgresql://unused", staging_dir=tmp_path, upload_key="")
        )


def test_the_sweep_removes_abandoned_uploads_and_their_files(
    client: TestClient, media: dict[str, Path], tmp_path: Path
) -> None:
    import psycopg

    from masdar.server import sweep_abandoned

    upload(client, media["original"])  # uploaded, never decided
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        connection.execute(f"SET search_path TO {SCHEMA}, public")
        connection.execute("UPDATE submission SET received_at = now() - interval '2 days'")

    assert sweep_abandoned(client.app) == 1  # type: ignore[arg-type]
    assert list((tmp_path / "staging").iterdir()) == []
    # The same clip can now be uploaded afresh instead of being refused as a duplicate.
    assert upload(client, media["original"])["status"] == "new"
