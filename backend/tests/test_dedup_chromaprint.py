"""The real fingerprint extractor, against the real fpcalc and real (generated) audio.

Skipped where fpcalc or ffmpeg is not installed. Test audio is synthesised by ffmpeg at
run time -- WORKFLOW.md: media never goes into git. Two gliding tones give Chromaprint
enough structure to tell recordings apart, which plain noise or a steady tone would not.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from maqati3.dedup.chromaprint import ChromaprintExtractor
from maqati3.dedup.fingerprint import UnreadableMedia, match_fingerprints

pytestmark = pytest.mark.skipif(
    shutil.which("fpcalc") is None or shutil.which("ffmpeg") is None,
    reason="integration test: needs fpcalc (chromaprint) and ffmpeg on PATH",
)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def tone(path: Path, f1: int, f2: int, r1: float, r2: float, seconds: int = 60) -> Path:
    """Two tones gliding around f1 and f2 at r1 and r2 rad/s.

    Chromaprint encodes how the pitch-class profile *changes*, so two signals with the
    same glide rates are a transposed copy of one movement to it, and match. Different
    content has to differ in time, not only in pitch -- as unrelated speech always does.
    """
    expr = (
        f"0.6*sin(2*PI*({f1}+150*sin(t*{r1}))*t)+0.4*sin(2*PI*({f2}+300*sin(t*{r2}))*t)"
    )
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':s=22050:d={seconds}", str(path))
    return path


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("media")
    original = tone(d / "original.wav", 220, 660, 1.3, 0.7)
    other = tone(d / "other.wav", 330, 500, 0.45, 1.9)
    reencoded = d / "forwarded.m4a"
    ffmpeg("-i", str(original), "-c:a", "aac", "-b:a", "64k", str(reencoded))
    phone = d / "phone.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=464x832:rate=30", "-i", str(reencoded),
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(phone),
    )
    no_audio = d / "screen_recording.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=464x832:rate=30", "-t", "3",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(no_audio))
    garbage = d / "not_a_video.mp4"
    garbage.write_bytes(b"a document renamed to .mp4")
    silence_a = d / "silence_a.wav"
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "30", str(silence_a))
    silence_b = d / "silence_b.m4a"
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "45",
           "-c:a", "aac", str(silence_b))
    return {
        "original": original,
        "other": other,
        "reencoded": reencoded,
        "phone": phone,
        "no_audio": no_audio,
        "garbage": garbage,
        "silence_a": silence_a,
        "silence_b": silence_b,
    }


EXTRACTOR = ChromaprintExtractor()


def test_a_recording_yields_items_and_its_duration(media: dict[str, Path]) -> None:
    fingerprint = EXTRACTOR.extract(media["original"])
    assert len(fingerprint.items) > 400  # ~8 items per second over 60 s
    assert abs(fingerprint.duration_ms - 60_000) <= 100
    assert all(0 <= item < 2**32 for item in fingerprint.items)


def test_the_audio_of_a_phone_video_is_read(media: dict[str, Path]) -> None:
    assert len(EXTRACTOR.extract(media["phone"]).items) > 400


def test_a_forwarded_copy_matches_its_original(media: dict[str, Path]) -> None:
    original = EXTRACTOR.extract(media["original"]).items
    for copy in ("reencoded", "phone"):
        result = match_fingerprints(original, EXTRACTOR.extract(media[copy]).items)
        assert result.matched is True, copy


def test_a_different_recording_does_not_match(media: dict[str, Path]) -> None:
    result = match_fingerprints(
        EXTRACTOR.extract(media["original"]).items, EXTRACTOR.extract(media["other"]).items
    )
    assert result.matched is False


def test_two_silent_recordings_do_not_match_each_other(media: dict[str, Path]) -> None:
    # Silence fingerprints as one value repeated. If that counted, every clip with a
    # quiet stretch would look like a duplicate of every other.
    result = match_fingerprints(
        EXTRACTOR.extract(media["silence_a"]).items, EXTRACTOR.extract(media["silence_b"]).items
    )
    assert result.matched is False


@pytest.mark.parametrize("name", ["no_audio", "garbage"])
def test_a_file_without_decodable_audio_is_unreadable(media: dict[str, Path], name: str) -> None:
    with pytest.raises(UnreadableMedia):
        EXTRACTOR.extract(media[name])


def test_a_missing_fpcalc_is_reported_as_such_not_as_bad_media(tmp_path: Path) -> None:
    # A broken server must not tell a contributor their perfectly good video is unreadable.
    with pytest.raises(FileNotFoundError):
        ChromaprintExtractor(fpcalc="/nonexistent/fpcalc").extract(tmp_path / "x.mp4")
