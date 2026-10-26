"""Dedup layer 1: the same online source submitted twice."""

import pytest

from maqati3.dedup.url import normalize_source_url


def test_input_that_is_not_a_url_is_flagged_instead_of_raising() -> None:
    result = normalize_source_url("just some words a brother typed")
    assert result.is_url is False
    assert result.platform_id is None


def test_youtube_watch_url_yields_platform_id_and_canonical_watch_url() -> None:
    result = normalize_source_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.is_url is True
    assert result.platform_id == "youtube:dQw4w9WgXcQ"
    assert result.canonical_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


YOUTUBE_SHAPES = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "http://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
    "https://www.youtube.com/live/dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=4",
    "https://youtu.be/dQw4w9WgXcQ?si=AbCdEfGhIjKl&t=42",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_source=telegram",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ#t=1m30s",
    "  https://www.youtube.com/watch?v=dQw4w9WgXcQ  ",
    "youtube.com/watch?v=dQw4w9WgXcQ",
    "www.youtube.com/watch?v=dQw4w9WgXcQ",
]


@pytest.mark.parametrize("shape", YOUTUBE_SHAPES)
def test_every_youtube_url_shape_collapses_onto_the_same_platform_id(shape: str) -> None:
    result = normalize_source_url(shape)
    assert result.platform_id == "youtube:dQw4w9WgXcQ"
    assert result.canonical_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert result.is_url is True


NOT_A_VIDEO = [
    "https://www.youtube.com/@IbnUthaymeenOfficial",
    "https://www.youtube.com/channel/UCabcdefghijklmnopqrstu",
    "https://www.youtube.com/playlist?list=PL1234567890",
    "https://www.youtube.com/watch?v=tooshort",
    "https://www.youtube.com/watch?v=waaaaaaaaaaaaytoolong",
    "https://www.youtube.com/watch?list=PL123",
    "https://youtu.be/",
    "https://www.youtube.com/shorts/not-an-id!",
]


@pytest.mark.parametrize("shape", NOT_A_VIDEO)
def test_youtube_url_without_a_well_formed_video_id_yields_no_platform_id(shape: str) -> None:
    assert normalize_source_url(shape).platform_id is None


def test_non_youtube_url_is_a_url_but_carries_no_platform_id() -> None:
    result = normalize_source_url("https://archive.org/details/fatwa-taharah-01")
    assert result.is_url is True
    assert result.platform_id is None
    assert result.canonical_url == "https://archive.org/details/fatwa-taharah-01"


def test_tracking_parameters_are_stripped_from_a_non_youtube_url() -> None:
    result = normalize_source_url(
        "https://example.org/audio/12?utm_source=whatsapp&utm_medium=share&fbclid=XYZ&si=ab"
    )
    assert result.canonical_url == "https://example.org/audio/12"


def test_meaningful_query_parameters_are_kept() -> None:
    result = normalize_source_url("https://example.org/play?id=441&utm_campaign=x")
    assert result.canonical_url == "https://example.org/play?id=441"


def test_fragment_is_removed() -> None:
    result = normalize_source_url("https://example.org/audio/12#section-3")
    assert result.canonical_url == "https://example.org/audio/12"


def test_host_is_lowercased() -> None:
    result = normalize_source_url("https://Example.ORG/Audio/12")
    assert result.canonical_url == "https://example.org/Audio/12"


def test_trailing_slash_is_normalised_away() -> None:
    assert normalize_source_url("https://example.org/audio/12/").canonical_url == (
        normalize_source_url("https://example.org/audio/12").canonical_url
    )


def test_a_non_youtube_host_is_never_given_a_youtube_platform_id() -> None:
    # Same path shape, different platform. Without a host check this would collide with
    # a real YouTube entry on the UNIQUE source_platform_id column.
    result = normalize_source_url("https://rumble.com/embed/dQw4w9WgXcQ")
    assert result.platform_id is None
    assert result.is_url is True


NOT_URLS = [
    "",
    "   ",
    "just some words a brother typed",
    "mailto:someone@example.org",
    "javascript:alert(1)",
    "ftp://example.org/file.mp3",
    "localhost:8000/audio",
    "the shaykh's lecture from last ramadan",
]


@pytest.mark.parametrize("junk", NOT_URLS)
def test_input_that_is_not_an_http_url_is_flagged_and_never_raises(junk: str) -> None:
    result = normalize_source_url(junk)
    assert result.is_url is False
    assert result.platform_id is None


def test_http_is_upgraded_to_https_so_both_schemes_share_one_key() -> None:
    assert normalize_source_url("http://example.org/audio/12").canonical_url == (
        normalize_source_url("https://example.org/audio/12").canonical_url
    )


def test_default_port_does_not_split_the_key() -> None:
    assert normalize_source_url("https://example.org:443/audio/12").canonical_url == (
        normalize_source_url("https://example.org/audio/12").canonical_url
    )


def test_query_parameter_order_does_not_split_the_key() -> None:
    assert normalize_source_url("https://example.org/p?a=1&b=2").canonical_url == (
        normalize_source_url("https://example.org/p?b=2&a=1").canonical_url
    )


def test_bare_host_without_a_path_keeps_a_root_slash() -> None:
    assert normalize_source_url("https://example.org").canonical_url == "https://example.org/"
