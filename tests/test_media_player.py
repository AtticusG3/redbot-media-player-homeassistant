"""Tests for media player entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
    RepeatMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.redbot_media_player.const import DOMAIN, LEGACY_HA_RED_RPC_METHODS
from custom_components.redbot_media_player.coordinator import RedRpcQueueCoordinator
from custom_components.redbot_media_player.media_player import (
    PARALLEL_UPDATES,
    RedDiscordMediaPlayer,
    _now_playing,
)
from custom_components.redbot_media_player.rpc import RedRpcError


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    e = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    e.add_to_hass(hass)
    return e


def test_parallel_updates_declared() -> None:
    """Media player platform uses explicit update parallelism."""
    assert PARALLEL_UPDATES == 1


@pytest.mark.asyncio
async def test_media_player_state_playing(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.state == MediaPlayerState.PLAYING


@pytest.mark.asyncio
async def test_media_image_url_from_coordinator(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    coord.media_image_url = "https://example.com/cover.jpg"
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.media_image_url == "https://example.com/cover.jpg"
    assert player.media_image_remotely_accessible is True


@pytest.mark.asyncio
async def test_supported_features_match_legacy_rpc_methods(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    """Older ha_red_rpc (no volume/skip/stop RPC) must not advertise those controls."""
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    coord.rpc_method_names = LEGACY_HA_RED_RPC_METHODS
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    feats = player.supported_features
    assert feats & MediaPlayerEntityFeature.PLAY
    assert feats & MediaPlayerEntityFeature.PAUSE
    assert feats & MediaPlayerEntityFeature.TURN_ON
    assert feats & MediaPlayerEntityFeature.TURN_OFF
    assert not (feats & MediaPlayerEntityFeature.VOLUME_SET)
    assert not (feats & MediaPlayerEntityFeature.NEXT_TRACK)
    assert not (feats & MediaPlayerEntityFeature.PREVIOUS_TRACK)
    assert not (feats & MediaPlayerEntityFeature.STOP)
    assert not (feats & MediaPlayerEntityFeature.SEEK)


@pytest.mark.asyncio
async def test_media_player_state_when_ok_false(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def not_ok(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {"ok": False, "queue": []}
        raise AssertionError(method)

    mock_rpc_call.side_effect = not_ok
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.state == MediaPlayerState.OFF


@pytest.mark.asyncio
async def test_async_media_play_pause_noop_when_idle(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def idle_queue(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": None,
                "queue": [],
                "voice_channel_id": 1234,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = idle_queue
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_media_play_pause()
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_media_player_state_idle(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def idle_queue(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": None,
                "queue": [],
                "voice_channel_id": 1234,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = idle_queue
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.state == MediaPlayerState.IDLE


@pytest.mark.asyncio
async def test_media_player_state_paused(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def paused_queue(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": True,
                "now_playing": {"title": "T"},
                "queue": [],
                "voice_channel_id": 1234,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = paused_queue
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.state == MediaPlayerState.PAUSED


@pytest.mark.asyncio
async def test_media_player_state_unknown_on_failed_update(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    from custom_components.redbot_media_player.rpc import RedRpcError

    mock_rpc_call.side_effect = RedRpcError("x")
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.state == MediaPlayerState.OFF


@pytest.mark.asyncio
async def test_media_player_state_off_when_not_in_voice(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def no_voice(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "voice_channel_id": None,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = no_voice
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.state == MediaPlayerState.OFF


def test_now_playing_helpers() -> None:
    assert _now_playing(None) is None
    assert _now_playing({}) is None
    assert _now_playing({"now_playing": "bad"}) is None
    assert _now_playing({"now_playing": {"title": "x"}})["title"] == "x"


@pytest.mark.asyncio
async def test_media_title_artist_prefers_left_right_split_over_author(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def split_queue(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {
                    "title": "Plan 9 feat. Jotj - You (Ben Sage Remix)",
                    "uri": "https://www.youtube.com/watch?v=6mDcM2mXfWA",
                    "author": "Leto Atreidis",
                    "length": 341000,
                },
                "queue": [],
                "guild_name": "G",
                "voice_channel_name": "VC",
                "voice_channel_id": 1,
                "shuffle": False,
                "repeat": False,
                "volume_percent": 16,
                "bot_self_mute": False,
                "bot_self_deaf": True,
            }
        if method == "GET_METHODS":
            return [
                "GET_METHODS",
                "HAREDRPC__QUEUE",
                "HAREDRPC__PLAY",
                "HAREDRPC__PAUSE",
            ]
        raise AssertionError(method)

    mock_rpc_call.side_effect = split_queue
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.media_artist == "Plan 9 feat. Jotj"
    assert player.media_title == "You (Ben Sage Remix)"
    assert player.extra_state_attributes["red_media_title"] == "Plan 9 feat. Jotj - You (Ben Sage Remix)"
    assert player.extra_state_attributes["red_media_author"] == "Leto Atreidis"


@pytest.mark.asyncio
async def test_media_title_artist_duration_attributes(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.media_title == "Test Track"
    assert player.media_artist == "Artist"
    assert player.media_content_id == "https://example.com/watch?v=1"
    assert player.media_duration == 120
    assert player.media_position == 15
    assert player.media_position_updated_at is not None
    assert player.extra_state_attributes == {
        "red_media_title": "Test Track",
        "red_media_author": "Artist",
        "queue_length": 1,
        "guild_name": "Test Guild",
        "voice_channel_name": "Riding Tunes",
        "voice_channel_id": 9001,
        "bot_self_mute": False,
        "bot_self_deaf": False,
    }
    assert player.volume_level == 0.5
    assert player.shuffle is False
    assert player.repeat == RepeatMode.OFF
    assert player.is_volume_muted is False


@pytest.mark.asyncio
async def test_media_duration_invalid_length(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def bad_len(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
                return {
                    "ok": True,
                    "paused": False,
                    "now_playing": {"title": "T", "author": "A", "length": "nope"},
                    "queue": "not-a-list",
                }
        raise AssertionError(method)

    mock_rpc_call.side_effect = bad_len
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.media_duration is None
    assert player.extra_state_attributes == {
        "red_media_title": "T",
        "red_media_author": "A",
    }


@pytest.mark.asyncio
async def test_async_media_play_skips_when_not_paused(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_media_play()
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_async_media_pause_skips_when_not_playing(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def idle_queue(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "paused": False, "now_playing": None, "queue": []}
        raise AssertionError(method)

    mock_rpc_call.side_effect = idle_queue
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_media_pause()
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_async_media_play_pause_toggle(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_media_play_pause()
    mock_rpc_call.assert_awaited()
    coord.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_async_play_media_refreshes(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_play_media("music", "search:foo")
    coord.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_async_play_media_rpc_error(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def se(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "voice_channel_id": 1234,
            }
        if method == "HAREDRPC__PLAY":
            raise RedRpcError("nope")
        raise AssertionError(method)

    mock_rpc_call.side_effect = se
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    with pytest.raises(HomeAssistantError):
        await player.async_play_media("music", "x")


@pytest.mark.asyncio
async def test_rpc_pause_rpc_error(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def se(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "voice_channel_id": 1234,
            }
        if method == "HAREDRPC__PAUSE":
            raise RedRpcError("pause-fail")
        raise AssertionError(method)

    mock_rpc_call.side_effect = se
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    with pytest.raises(HomeAssistantError):
        await player.async_media_play_pause()


@pytest.mark.asyncio
async def test_device_info_uses_voice_channel_name(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.device_info["name"] == "Riding Tunes"


@pytest.mark.asyncio
async def test_device_info_falls_back_to_guild_when_no_voice(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def no_voice(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "T"},
                "queue": [],
                "guild_name": "Only Guild",
                "voice_channel_name": None,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = no_voice
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.device_info["name"] == "Only Guild"


@pytest.mark.asyncio
async def test_async_media_stop_calls_rpc(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_media_stop()
    mock_rpc_call.assert_awaited()
    calls = [c.args[2] for c in mock_rpc_call.await_args_list]
    assert "HAREDRPC__STOP" in calls


@pytest.mark.asyncio
async def test_async_turn_on_calls_summon(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_turn_on()
    calls = [c.args[2] for c in mock_rpc_call.await_args_list]
    assert "HAREDRPC__SUMMON" in calls


@pytest.mark.asyncio
async def test_async_turn_off_calls_disconnect(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_turn_off()
    calls = [c.args[2] for c in mock_rpc_call.await_args_list]
    assert "HAREDRPC__DISCONNECT" in calls


@pytest.mark.asyncio
async def test_async_set_volume_level(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_set_volume_level(0.25)
    last = mock_rpc_call.await_args
    assert last[0][2] == "HAREDRPC__VOLUME"
    assert last[0][3] == [1, 2, 3, 25]


@pytest.mark.asyncio
async def test_async_mute_unmute_volume(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_mute_volume(True)
    await player.async_mute_volume(False)
    vol_calls = [c for c in mock_rpc_call.await_args_list if c[0][2] == "HAREDRPC__VOLUME"]
    assert len(vol_calls) >= 2
    assert vol_calls[-2][0][3][3] == 1
    assert vol_calls[-1][0][3][3] == 50


@pytest.mark.asyncio
async def test_async_set_shuffle_toggles_when_needed(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def data(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "shuffle": False,
            }
        if method == "HAREDRPC__SHUFFLE":
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = data
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_set_shuffle(True)
    assert any(c[0][2] == "HAREDRPC__SHUFFLE" for c in mock_rpc_call.await_args_list)


@pytest.mark.asyncio
async def test_async_set_repeat_toggles_when_needed(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def data(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "repeat": False,
            }
        if method == "HAREDRPC__REPEAT":
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = data
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_set_repeat(RepeatMode.ALL)
    assert any(c[0][2] == "HAREDRPC__REPEAT" for c in mock_rpc_call.await_args_list)


@pytest.mark.asyncio
async def test_async_media_seek_calls_seek_rpc(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_media_seek(42.6)
    calls = [c for c in mock_rpc_call.await_args_list if c[0][2] == "HAREDRPC__SEEK"]
    assert calls
    assert calls[-1][0][3] == [1, 2, 3, 28]


@pytest.mark.asyncio
async def test_async_media_seek_calls_negative_delta_for_backward_seek(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_media_seek(3)
    calls = [c for c in mock_rpc_call.await_args_list if c[0][2] == "HAREDRPC__SEEK"]
    assert calls
    assert calls[-1][0][3] == [1, 2, 3, -12]


@pytest.mark.asyncio
async def test_device_info_when_update_failed_uses_entry_title(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.last_update_success = False
    assert player.device_info["name"] == "Test"


@pytest.mark.asyncio
async def test_media_duration_none_without_length(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "T"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.media_duration is None


@pytest.mark.asyncio
async def test_volume_shuffle_repeat_none_when_absent(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "T"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.volume_level is None
    assert player.is_volume_muted is None
    assert player.shuffle is None
    assert player.repeat is None


@pytest.mark.asyncio
async def test_async_set_shuffle_noop_when_false_and_unknown(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_set_shuffle(False)
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_async_set_repeat_noop_off_when_unknown(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_set_repeat(RepeatMode.OFF)
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_async_set_shuffle_noop_when_already_on(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "shuffle": True,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_set_shuffle(True)
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_async_media_play_when_paused(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": True,
                "now_playing": {"title": "t"},
                "queue": [],
                "voice_channel_id": 1234,
            }
        if method == "HAREDRPC__PAUSE":
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_media_play()
    assert any(c[0][2] == "HAREDRPC__PAUSE" for c in mock_rpc_call.await_args_list)


@pytest.mark.asyncio
async def test_async_media_pause_when_playing(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_media_pause()
    mock_rpc_call.assert_awaited()


@pytest.mark.asyncio
async def test_async_clear_playlist_and_next_track_rpc(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_clear_playlist()
    await player.async_media_next_track()
    methods = [c[0][2] for c in mock_rpc_call.await_args_list]
    assert "HAREDRPC__QUEUE_CLEAR" in methods
    assert "HAREDRPC__SKIP" in methods


@pytest.mark.asyncio
async def test_async_media_previous_track_rpc(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_media_previous_track()
    methods = [c[0][2] for c in mock_rpc_call.await_args_list]
    assert "HAREDRPC__PREVIOUS" in methods


@pytest.mark.asyncio
async def test_async_media_previous_track_rpc_error(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        if method == "HAREDRPC__PREVIOUS":
            raise RedRpcError("prev-fail")
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    with pytest.raises(HomeAssistantError):
        await player.async_media_previous_track()


@pytest.mark.asyncio
async def test_async_media_previous_track_rpc_command_error_result(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        if method == "HAREDRPC__PREVIOUS":
            return {"ok": False, "error": "invalid_command", "detail": "previous"}
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    with pytest.raises(HomeAssistantError, match="invalid_command"):
        await player.async_media_previous_track()


@pytest.mark.asyncio
async def test_async_set_volume_level_rpc_error(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "volume_percent": 10,
            }
        if method == "HAREDRPC__VOLUME":
            raise RedRpcError("vol-fail")
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    with pytest.raises(HomeAssistantError):
        await player.async_set_volume_level(0.2)


@pytest.mark.asyncio
async def test_async_media_stop_rpc_error(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        if method == "HAREDRPC__STOP":
            raise RedRpcError("stop-fail")
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    with pytest.raises(HomeAssistantError):
        await player.async_media_stop()


@pytest.mark.asyncio
async def test_red_raw_attributes_title_only_and_author_only(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def title_only(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "T"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = title_only
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.extra_state_attributes["red_media_title"] == "T"
    assert "red_media_author" not in player.extra_state_attributes

    async def author_only(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"author": "A"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = author_only
    await coord.async_refresh()
    assert player.extra_state_attributes["red_media_author"] == "A"
    assert "red_media_title" not in player.extra_state_attributes


@pytest.mark.asyncio
async def test_extra_state_attributes_empty_when_data_not_dict(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    coord.data = [1, 2, 3]  # type: ignore[assignment]
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.extra_state_attributes == {}


@pytest.mark.asyncio
async def test_volume_level_none_when_percent_key_missing_vs_explicit_none(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "volume_percent": None,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.volume_level is None


@pytest.mark.asyncio
async def test_async_unmute_volume_delegates(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    player.async_mute_volume = AsyncMock()
    await player.async_unmute_volume()
    player.async_mute_volume.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_async_set_shuffle_calls_rpc_when_unknown_and_want_on(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        if method == "HAREDRPC__SHUFFLE":
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_set_shuffle(True)
    assert any(c[0][2] == "HAREDRPC__SHUFFLE" for c in mock_rpc_call.await_args_list)


@pytest.mark.asyncio
async def test_async_set_repeat_calls_rpc_when_unknown_and_want_on(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        if method == "HAREDRPC__REPEAT":
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_set_repeat(RepeatMode.ALL)
    assert any(c[0][2] == "HAREDRPC__REPEAT" for c in mock_rpc_call.await_args_list)


@pytest.mark.asyncio
async def test_async_set_shuffle_noop_when_unknown_and_want_off(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_set_shuffle(False)
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_async_set_repeat_noop_when_unknown_and_want_off(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_set_repeat(RepeatMode.OFF)
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_async_set_repeat_noop_when_already_matches(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "repeat": True,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    before = mock_rpc_call.await_count
    await player.async_set_repeat(RepeatMode.ALL)
    assert mock_rpc_call.await_count == before


@pytest.mark.asyncio
async def test_volume_level_invalid_percent_coerces_none(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
                "volume_percent": "bad",
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    assert player.volume_level is None


@pytest.mark.asyncio
async def test_async_mute_without_prior_volume_uses_default_unmute(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def q(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {"title": "t"},
                "queue": [],
            }
        if method == "HAREDRPC__VOLUME":
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = q
    entry = _entry(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    player = RedDiscordMediaPlayer(coord, entry)
    coord.async_request_refresh = AsyncMock()
    await player.async_mute_volume(True)
    await player.async_mute_volume(False)
    vol_calls = [c for c in mock_rpc_call.await_args_list if c[0][2] == "HAREDRPC__VOLUME"]
    assert vol_calls[-1][0][3][3] == 50
