"""Dedup layer 1: normalise a submitted source URL so the same link submitted twice
collapses onto one key.

See docs/PIPELINE.md section 2, layer 1. This is the cheapest layer and catches the most
common case by far: two brothers submit the same link.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_YOUTUBE_HOSTS = frozenset({"youtube.com", "youtu.be", "youtube-nocookie.com"})

# A YouTube video id is exactly 11 characters of the URL-safe base64 alphabet. Checking
# the shape matters: without it any path segment would be accepted as an id and two
# unrelated links could collide on the UNIQUE source_platform_id column.
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

_YOUTUBE_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/", "/v/")

_HAS_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

# A host must have at least one dot and an alphabetic TLD, otherwise the submission was
# free text, not a link.
_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")

# Only parameters that are unambiguously tracking. Anything that might identify the
# recording itself stays: dropping a meaningful parameter would merge two distinct
# sources onto one key, which is the one mistake this layer must not make.
_TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "si",
        "yclid",
    }
)
_TRACKING_PREFIXES = ("utm_",)


@dataclass(frozen=True)
class NormalizedSource:
    """The result of normalising one submitted source string.

    ``platform_id`` is the value for ``entry.source_platform_id`` (UNIQUE in the schema)
    and is only set when the URL identifies a recording on a known platform.
    ``is_url`` is false when the submission was not a usable http(s) URL at all; callers
    must not store ``canonical_url`` as a source in that case.
    """

    canonical_url: str
    platform_id: str | None
    is_url: bool


def _bare_host(netloc: str) -> str:
    host = netloc.split("@")[-1].split(":")[0].lower()
    for prefix in ("www.", "m.", "music."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _youtube_video_id(host: str, path: str, query: list[tuple[str, str]]) -> str | None:
    if host not in _YOUTUBE_HOSTS:
        return None
    if host == "youtu.be":
        candidate = path.lstrip("/").split("/")[0]
        return candidate if _YOUTUBE_ID.match(candidate) else None
    if path == "/watch":
        for key, value in query:
            if key == "v" and _YOUTUBE_ID.match(value):
                return value
        return None
    for prefix in _YOUTUBE_PATH_PREFIXES:
        if path.startswith(prefix):
            candidate = path[len(prefix) :].split("/")[0]
            return candidate if _YOUTUBE_ID.match(candidate) else None
    return None


def _with_scheme(raw: str) -> str:
    """People paste links without a scheme. Treat a bare host as https."""
    if _HAS_SCHEME.match(raw):
        return raw
    return "https://" + raw.lstrip("/")


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in _TRACKING_PARAMS or lowered.startswith(_TRACKING_PREFIXES)


def _normalize_netloc(netloc: str) -> str:
    userinfo, _, hostport = netloc.rpartition("@")
    host, _, port = hostport.partition(":")
    host = host.lower().rstrip(".")
    rendered = host if port in ("", "80", "443") else f"{host}:{port}"
    return f"{userinfo}@{rendered}" if userinfo else rendered


def _normalize_path(path: str) -> str:
    stripped = path.rstrip("/")
    return stripped if stripped else "/"


def normalize_source_url(url: str) -> NormalizedSource:
    raw = _with_scheme(url.strip())
    parts = urlsplit(raw)
    host = _bare_host(parts.netloc)
    query = parse_qsl(parts.query, keep_blank_values=True)

    video_id = _youtube_video_id(host, parts.path, query)
    if video_id is not None:
        return NormalizedSource(
            canonical_url=f"https://www.youtube.com/watch?v={video_id}",
            platform_id=f"youtube:{video_id}",
            is_url=True,
        )

    if parts.scheme.lower() not in ("http", "https") or not _HOST.match(host):
        return NormalizedSource(canonical_url=url.strip(), platform_id=None, is_url=False)

    kept = sorted((k, v) for k, v in query if not _is_tracking(k))
    canonical = urlunsplit(
        (
            "https",
            _normalize_netloc(parts.netloc),
            _normalize_path(parts.path),
            urlencode(kept),
            "",
        )
    )
    return NormalizedSource(canonical_url=canonical, platform_id=None, is_url=True)


__all__ = ["NormalizedSource", "normalize_source_url"]
