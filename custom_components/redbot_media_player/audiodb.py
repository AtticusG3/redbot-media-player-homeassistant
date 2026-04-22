"""TheAudioDB (theaudiodb.com) lookup for album / track artwork."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

AUDIODB_BASE = "https://www.theaudiodb.com/api/v1/json"
# Public test key (v1 JSON API); Patreon keys replace rate limits.
DEFAULT_AUDIODB_API_KEY = "2"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


def _sanitize_artist(author: str) -> str:
    """Normalize Lavalink / YouTube-style author strings."""
    s = (author or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low.endswith(" - topic"):
        s = s[: -len(" - topic")].strip()
    return s


def _sanitize_title(title: str, artist: str) -> str:
    """Strip noise; drop ``Artist - `` prefix when it matches ``artist``."""
    s = (title or "").strip()
    if not s:
        return ""
    art = _sanitize_artist(artist)
    if art and " - " in s:
        prefix, rest = s.split(" - ", 1)
        if prefix.strip().lower() == art.lower():
            return rest.strip()
    return s


def _split_title_artist_track(title: str) -> tuple[str, str] | None:
    """If ``title`` looks like ``Artist - Track``, return both parts."""
    s = (title or "").strip()
    if " - " not in s:
        return None
    left, right = s.split(" - ", 1)
    left, right = left.strip(), right.strip()
    if not right or len(left) > 80:
        return None
    return left, right


# Trailing YouTube-style labels (not ``(feat. ...)`` credits).
_YOUTUBE_PROMO_PAREN = re.compile(
    r"""
    \s*
    \(
        \s*
        (?:
            Official(?:\s+HD)?(?:\s+Music)?\s+Video
            | Official\s+Music\s+Video
            | Official\s+HD\s+Video
            | Official\s+Video
            | Official\s+Audio
            | Official\s+Visuali[sz]er
            | (?:360\S*\s+)?Visuali[sz]er
            | Lyric\s+Video
            | Lyrics
        )
        \s*
    \)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_LEADING_BRACKET_TAG = re.compile(r"^\[[^\[\]]+\]\s*-\s*")
_TRAILING_PROMO_BRACKET = re.compile(
    r"""
    \s*
    \[
        \s*
        (?:
            .*?(?:release|official|lyrics?|lyric|audio|video|visualizer|premiere|hq|hd).*
            | .*?monstercat.*?
        )
        \s*
    \]
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_youtube_promotional_title_suffix(title: str) -> str:
    """Remove trailing ``(Official ... Video)``-style labels from a track title."""
    s = (title or "").strip()
    while True:
        n = _YOUTUBE_PROMO_PAREN.sub("", s)
        if n == s:
            return n.strip()
        s = n.strip()


def strip_leading_bracket_tags(text: str) -> str:
    """Remove repeated ``[Tag] - `` prefixes from a title."""
    s = (text or "").strip()
    while True:
        n = _LEADING_BRACKET_TAG.sub("", s)
        if n == s:
            return n.strip()
        s = n.strip()


def strip_trailing_bracket_promo_suffix(title: str) -> str:
    """Remove trailing ``[... Release]``/promo labels from track title."""
    s = (title or "").strip()
    while True:
        n = _TRAILING_PROMO_BRACKET.sub("", s)
        if n == s:
            return n.strip()
        s = n.strip()


def normalize_display_metadata(author: str, title: str) -> tuple[str, str]:
    """Raw Red author/title -> display ``media_artist`` / ``media_title``."""
    s_author = _sanitize_artist(author)
    s_title = strip_leading_bracket_tags((title or "").strip())
    parts = [p.strip() for p in s_title.split(" - ")]
    if len(parts) >= 2 and parts[0] and any(p for p in parts[1:]):
        artist = parts[0]
        track = " - ".join(p for p in parts[1:] if p)
    else:
        artist = s_author
        track = _sanitize_title(s_title, s_author)
    track = strip_trailing_bracket_promo_suffix(track)
    track = strip_youtube_promotional_title_suffix(track)
    track = _strip_wrapping_quotes(track)
    return artist, track


def _strip_wrapping_quotes(text: str) -> str:
    """Remove wrapping quote punctuation repeatedly from a title."""
    s = (text or "").strip()
    wrappers = "\"'`"
    while len(s) >= 2 and s[0] in wrappers and s[-1] in wrappers:
        s = s[1:-1].strip()
    return s


def _first_non_empty(d: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


async def async_fetch_album_art_url(
    hass: HomeAssistant,
    api_key: str,
    author: str,
    title: str,
) -> str | None:
    """
    Resolve cover art URL using TheAudioDB searchtrack (+ optional album lookup).

    Parameters
    ----------
    hass
        Home Assistant instance (used for the shared aiohttp client session).
    api_key
        v1 API key in the URL path (free test key or Patreon key).
    author, title
        From Red / Lavalink ``now_playing`` (``author`` / ``title``).
    """
    author, title = normalize_display_metadata(author, title)
    session = async_get_clientsession(hass)
    artist = _sanitize_artist(author)
    track = _sanitize_title(title, author)

    split = _split_title_artist_track(title)
    if not artist and split:
        artist, track = split[0], split[1]

    if not track:
        return None
    if not artist:
        return None

    key = (api_key or "").strip() or DEFAULT_AUDIODB_API_KEY

    async def _get_json(path: str, params: dict[str, str]) -> Any:
        url = f"{AUDIODB_BASE}/{quote(key, safe='')}/{path}"
        async with session.get(url, params=params, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                _LOGGER.debug("TheAudioDB HTTP %s for %s", resp.status, path)
                return None
            return await resp.json(content_type=None)

    try:
        data = await _get_json(
            "searchtrack.php",
            {"s": artist, "t": track},
        )
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("TheAudioDB searchtrack failed: %s", err)
        return None

    track_row = _extract_first_track(data)
    if track_row is None:
        return None

    thumb = _first_non_empty(track_row, "strTrackThumb")
    if thumb:
        return thumb

    album_id = track_row.get("idAlbum")
    if album_id is None:
        return None
    try:
        mid = str(int(str(album_id)))
    except (TypeError, ValueError):
        return None

    try:
        album_data = await _get_json("album.php", {"m": mid})
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("TheAudioDB album lookup failed: %s", err)
        return None

    album_row = _extract_first_album(album_data)
    if album_row is None:
        return None
    return _first_non_empty(
        album_row,
        "strAlbumThumbHQ",
        "strAlbumThumb",
    )


def _extract_first_track(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    tracks = data.get("track")
    if not isinstance(tracks, list) or not tracks:
        return None
    first = tracks[0]
    return first if isinstance(first, dict) else None


def _extract_first_album(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    albums = data.get("album")
    if not isinstance(albums, list) or not albums:
        return None
    first = albums[0]
    return first if isinstance(first, dict) else None
