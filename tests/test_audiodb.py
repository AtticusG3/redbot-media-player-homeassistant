"""Tests for TheAudioDB artwork lookup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.redbot_media_player.audiodb import (
    async_fetch_album_art_url,
    normalize_display_metadata,
    strip_leading_bracket_tags,
    strip_trailing_bracket_promo_suffix,
    strip_youtube_promotional_title_suffix,
    _extract_first_album,
    _extract_first_track,
    _sanitize_artist,
    _sanitize_title,
    _split_title_artist_track,
)


def test_sanitize_artist_strips_topic_suffix() -> None:
    assert _sanitize_artist("Some Band - Topic") == "Some Band"


def test_sanitize_title_drops_matching_artist_prefix() -> None:
    assert (
        _sanitize_title("Coldplay - Yellow", "Coldplay") == "Yellow"
    )


def test_sanitize_title_empty() -> None:
    assert _sanitize_title("", "Coldplay") == ""


def test_split_title_rejects_long_left_segment() -> None:
    long_left = "x" * 81
    assert _split_title_artist_track(f"{long_left} - y") is None


@pytest.mark.asyncio
async def test_fetch_uses_split_when_author_empty(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Artist - Title`` in title fills artist when author is empty."""
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "idAlbum": "1",
                    "strTrackThumb": "https://cdn.example/from-split.jpg",
                }
            ]
        }
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    url = await async_fetch_album_art_url(
        hass,  # type: ignore[arg-type]
        "2",
        "",
        "Coldplay - Yellow",
    )
    assert url == "https://cdn.example/from-split.jpg"


@pytest.mark.asyncio
async def test_fetch_returns_none_empty_title(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )
    assert await async_fetch_album_art_url(hass, "2", "Coldplay", "") is None  # type: ignore[arg-type]
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_retry_search_exception_swallowed(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second searchtrack may fail with network error; returns None."""

    def make_cm(payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=payload)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    calls = 0

    def get_side_effect(url: str, **_kwargs: object) -> MagicMock:
        nonlocal calls
        calls += 1
        if "searchtrack" in url and calls == 1:
            return make_cm({"track": None})
        if "searchtrack" in url and calls == 2:
            raise TimeoutError("retry-fail")
        raise AssertionError((url, calls))

    session = MagicMock()
    session.get = MagicMock(side_effect=get_side_effect)
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    url = await async_fetch_album_art_url(
        hass,  # type: ignore[arg-type]
        "2",
        "Wrong",
        "Coldplay - Yellow",
    )
    assert url is None


@pytest.mark.asyncio
async def test_fetch_album_when_id_album_missing(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "strTrackThumb": "",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )
    assert (
        await async_fetch_album_art_url(
            hass,  # type: ignore[arg-type]
            "2",
            "Coldplay",
            "Yellow",
        )
        is None
    )


@pytest.mark.asyncio
async def test_fetch_album_invalid_id_skips_album_call(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "idAlbum": "not-int",
                    "strTrackThumb": "",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )
    assert (
        await async_fetch_album_art_url(
            hass,  # type: ignore[arg-type]
            "2",
            "Coldplay",
            "Yellow",
        )
        is None
    )


@pytest.mark.asyncio
async def test_fetch_album_http_exception(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    track_payload = {
        "track": [
            {
                "idAlbum": "2109615",
                "strTrackThumb": "",
            }
        ]
    }

    def make_cm(payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=payload)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    def get_side_effect(url: str, **_kwargs: object) -> MagicMock:
        if "searchtrack" in url:
            return make_cm(track_payload)
        if "album.php" in url:
            raise aiohttp.ClientError("album-down")
        raise AssertionError(url)

    session = MagicMock()
    session.get = MagicMock(side_effect=get_side_effect)
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    assert (
        await async_fetch_album_art_url(
            hass,  # type: ignore[arg-type]
            "2",
            "Coldplay",
            "Yellow",
        )
        is None
    )


@pytest.mark.asyncio
async def test_fetch_album_row_missing(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "idAlbum": "2109615",
                    "strTrackThumb": "",
                }
            ]
        },
        album_json={"album": None},
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )
    assert (
        await async_fetch_album_art_url(
            hass,  # type: ignore[arg-type]
            "2",
            "Coldplay",
            "Yellow",
        )
        is None
    )


def test_extract_first_track_edge_cases() -> None:
    assert _extract_first_track("not-dict") is None
    assert _extract_first_track({"track": []}) is None
    assert _extract_first_track({"track": ["bad"]}) is None


def test_extract_first_album_edge_cases() -> None:
    assert _extract_first_album("not-dict") is None
    assert _extract_first_album({"album": []}) is None
    assert _extract_first_album({"album": ["bad"]}) is None


def test_normalize_display_uses_left_right_split_with_mismatched_author() -> None:
    artist, title = normalize_display_metadata(
        "Leto Atreidis",
        "Plan 9 feat. Jotj - You (Ben Sage Remix)",
    )
    assert artist == "Plan 9 feat. Jotj"
    assert title == "You (Ben Sage Remix)"


def test_strip_youtube_promotional_suffix() -> None:
    assert (
        strip_youtube_promotional_title_suffix(
            "Bodies (Official HD Music Video)"
        )
        == "Bodies"
    )
    assert strip_youtube_promotional_title_suffix("Song (feat. X)") == "Song (feat. X)"


def test_strip_leading_bracket_tags() -> None:
    assert (
        strip_leading_bracket_tags("[Electronic] - [DnB] - Fractal - Fire Away")
        == "Fractal - Fire Away"
    )


def test_strip_trailing_bracket_promo_suffix() -> None:
    assert (
        strip_trailing_bracket_promo_suffix(
            "Fire Away (feat. Danyka Nadeau) [Monstercat LP Release]"
        )
        == "Fire Away (feat. Danyka Nadeau)"
    )
    assert strip_trailing_bracket_promo_suffix("Song [Live]") == "Song [Live]"


def test_normalize_display_strips_artist_prefix_and_promo() -> None:
    artist, title = normalize_display_metadata(
        "Drowning Pool",
        "Drowning Pool - Bodies (Official HD Music Video)",
    )
    assert artist == "Drowning Pool"
    assert title == "Bodies"


def test_normalize_display_strips_genre_prefix_and_release_suffix() -> None:
    artist, title = normalize_display_metadata(
        "Monstercat: Uncaged",
        "[Electronic] - Fractal - Fire Away (feat. Danyka Nadeau) [Monstercat LP Release]",
    )
    assert artist == "Fractal"
    assert title == "Fire Away (feat. Danyka Nadeau)"


def test_normalize_display_no_separator_uses_author_and_sanitize_title() -> None:
    artist, title = normalize_display_metadata(
        "Drowning Pool",
        "Drowning Pool - Bodies (Official HD Music Video)",
    )
    assert artist == "Drowning Pool"
    assert title == "Bodies"


def test_normalize_display_strips_visualiser_suffix() -> None:
    artist, title = normalize_display_metadata(
        "Joji",
        "Joji - LOVE YOU LESS (360° Visualizer)",
    )
    assert artist == "Joji"
    assert title == "LOVE YOU LESS"


def test_normalize_display_strips_wrapping_quotes() -> None:
    artist, title = normalize_display_metadata(
        "Harry Hayes",
        "Harry Hayes - '''I Did You Wrong'''",
    )
    assert artist == "Harry Hayes"
    assert title == "I Did You Wrong"


def _mock_session_get(
    track_json: dict | None = None, album_json: dict | None = None
) -> MagicMock:
    """Build session.get that returns async context managers with JSON bodies."""
    track_json = track_json or {}
    album_json = album_json or {}

    def make_cm(payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=payload)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    def get_side_effect(url: str, **_kwargs: object) -> MagicMock:
        if "searchtrack" in url:
            return make_cm(track_json)
        if "album.php" in url:
            return make_cm(album_json)
        raise AssertionError(url)

    session = MagicMock()
    session.get = MagicMock(side_effect=get_side_effect)
    return session


@pytest.mark.asyncio
async def test_fetch_returns_track_thumb_when_present(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "idAlbum": "1",
                    "strTrackThumb": "https://cdn.example/track.jpg",
                }
            ]
        }
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    url = await async_fetch_album_art_url(
        hass,  # type: ignore[arg-type]
        "2",
        "Coldplay",
        "Yellow",
    )
    assert url == "https://cdn.example/track.jpg"
    session.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_album_when_no_track_thumb(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "idAlbum": "2109615",
                    "strTrackThumb": "",
                }
            ]
        },
        album_json={
            "album": [
                {
                    "strAlbumThumb": "https://cdn.example/album.jpg",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    url = await async_fetch_album_art_url(
        hass,  # type: ignore[arg-type]
        "2",
        "Coldplay",
        "Yellow",
    )
    assert url == "https://cdn.example/album.jpg"
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_returns_none_without_artist(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = MagicMock()
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )
    assert await async_fetch_album_art_url(hass, "2", "", "Yellow") is None  # type: ignore[arg-type]
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_no_retry_when_split_based_lookup_misses(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With split-first metadata, miss on searchtrack returns None directly."""

    def make_cm(payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=payload)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    calls: list[list[str]] = []

    def get_side_effect(url: str, **_kwargs: object) -> MagicMock:
        calls.append([url])
        return make_cm({"track": None})

    session = MagicMock()
    session.get = MagicMock(side_effect=get_side_effect)
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    url = await async_fetch_album_art_url(
        hass,  # type: ignore[arg-type]
        "2",
        "Wrong",
        "Coldplay - Yellow",
    )
    assert url is None
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_fetch_returns_none_on_http_error(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    resp = MagicMock()
    resp.status = 404
    resp.json = AsyncMock(return_value={})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    assert (
        await async_fetch_album_art_url(
            hass,  # type: ignore[arg-type]
            "2",
            "Coldplay",
            "Yellow",
        )
        is None
    )


@pytest.mark.asyncio
async def test_fetch_prefers_album_hq_thumb(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "idAlbum": "2109615",
                    "strTrackThumb": "",
                }
            ]
        },
        album_json={
            "album": [
                {
                    "strAlbumThumbHQ": "https://cdn.example/hq.jpg",
                    "strAlbumThumb": "https://cdn.example/album.jpg",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    url = await async_fetch_album_art_url(
        hass,  # type: ignore[arg-type]
        "2",
        "Coldplay",
        "Yellow",
    )
    assert url == "https://cdn.example/hq.jpg"


@pytest.mark.asyncio
async def test_fetch_json_error_on_track_search(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(side_effect=ValueError("bad json"))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    assert (
        await async_fetch_album_art_url(
            hass,  # type: ignore[arg-type]
            "2",
            "Coldplay",
            "Yellow",
        )
        is None
    )


@pytest.mark.asyncio
async def test_fetch_skips_album_when_id_invalid(
    hass: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _mock_session_get(
        track_json={
            "track": [
                {
                    "idAlbum": "not-a-number",
                    "strTrackThumb": "",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.audiodb.async_get_clientsession",
        MagicMock(return_value=session),
    )

    assert (
        await async_fetch_album_art_url(
            hass,  # type: ignore[arg-type]
            "2",
            "Coldplay",
            "Yellow",
        )
        is None
    )
