"""Media player entity backed by Red Audio (HAREDRPC__)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    RepeatMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .audiodb import normalize_display_metadata
from .coordinator import RedRpcQueueCoordinator
from .helpers import device_info_for_red_entry, get_rpc_params
from .rpc import RedRpcError, rpc_call

_LOGGER = logging.getLogger(__name__)
_MUTED_VOLUME_LEVEL = 0.01
PARALLEL_UPDATES = 1


def _now_playing(data: Any) -> dict[str, Any] | None:
    """Return the now_playing dict from coordinator data, or None."""
    if not isinstance(data, dict):
        return None
    np = data.get("now_playing")
    return np if isinstance(np, dict) else None


def _raise_on_rpc_result_error(method: str, result: Any) -> None:
    """Raise when an RPC command returns a structured command failure."""
    if not isinstance(result, dict):
        return
    if result.get("ok", True):
        return
    detail = result.get("detail")
    err = result.get("error", "command_failed")
    if detail is None:
        raise HomeAssistantError(f"RedBot Media Player {method} failed: {err}")
    raise HomeAssistantError(f"RedBot Media Player {method} failed: {err} ({detail})")


def _supported_features_for_rpc(methods: frozenset[str]) -> MediaPlayerEntityFeature:
    """Expose HA controls only for RPC methods the Red cog actually registered."""
    f = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.PLAY_MEDIA
    )
    if "HAREDRPC__SUMMON" in methods:
        f |= MediaPlayerEntityFeature.TURN_ON
    if "HAREDRPC__DISCONNECT" in methods:
        f |= MediaPlayerEntityFeature.TURN_OFF
    if "HAREDRPC__STOP" in methods:
        f |= MediaPlayerEntityFeature.STOP
    if "HAREDRPC__SKIP" in methods:
        f |= MediaPlayerEntityFeature.NEXT_TRACK
    if "HAREDRPC__PREVIOUS" in methods:
        f |= MediaPlayerEntityFeature.PREVIOUS_TRACK
    if "HAREDRPC__QUEUE_CLEAR" in methods:
        f |= MediaPlayerEntityFeature.CLEAR_PLAYLIST
    if "HAREDRPC__VOLUME" in methods:
        f |= (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )
    if "HAREDRPC__SHUFFLE" in methods:
        f |= MediaPlayerEntityFeature.SHUFFLE_SET
    if "HAREDRPC__REPEAT" in methods:
        f |= MediaPlayerEntityFeature.REPEAT_SET
    if "HAREDRPC__SEEK" in methods:
        f |= MediaPlayerEntityFeature.SEEK
    return MediaPlayerEntityFeature(f)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Red Discord media player from a config entry."""
    coordinator: RedRpcQueueCoordinator = entry.runtime_data
    async_add_entities([RedDiscordMediaPlayer(coordinator, entry)])


class RedDiscordMediaPlayer(CoordinatorEntity[RedRpcQueueCoordinator], MediaPlayerEntity):
    """Represents Red Audio playback state via JSON-RPC queue polling."""

    _attr_has_entity_name = True
    _attr_translation_key = "red_discord_audio"

    def __init__(self, coordinator: RedRpcQueueCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._restore_volume_level: float | None = None

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Depends on ha_red_rpc version on the bot (GET_METHODS at setup)."""
        return _supported_features_for_rpc(self.coordinator.effective_rpc_methods)

    @property
    def device_info(self) -> DeviceInfo:
        """Name device from Discord voice channel or guild when available."""
        return device_info_for_red_entry(
            self._entry,
            data=self.coordinator.data if self.coordinator.last_update_success else None,
            last_update_success=self.coordinator.last_update_success,
        )

    @property
    def state(self) -> MediaPlayerState | None:
        """Map queue payload to HA media state."""
        if not self._is_powered_on():
            return MediaPlayerState.OFF
        if not self.coordinator.data:
            return MediaPlayerState.OFF
        data = self.coordinator.data
        if not data.get("ok"):
            return MediaPlayerState.OFF
        if not data.get("now_playing"):
            return MediaPlayerState.IDLE
        if data.get("paused"):
            return MediaPlayerState.PAUSED
        return MediaPlayerState.PLAYING

    def _is_powered_on(self) -> bool:
        """Power is on only when RPC is reachable and bot is in voice."""
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data
        if not isinstance(data, dict):
            return False
        if not data.get("ok"):
            return False
        return bool(data.get("voice_channel_id"))

    @property
    def media_title(self) -> str | None:
        """Track title after normalizing Red/Lavalink metadata."""
        np = _now_playing(self.coordinator.data)
        if not np:
            return None
        raw_title = str(np.get("title") or "")
        raw_author = str(np.get("author") or "")
        _, title = normalize_display_metadata(raw_author, raw_title)
        return title

    @property
    def media_artist(self) -> str | None:
        """Artist after normalizing Red/Lavalink metadata."""
        np = _now_playing(self.coordinator.data)
        if not np:
            return None
        raw_title = str(np.get("title") or "")
        raw_author = str(np.get("author") or "")
        artist, _ = normalize_display_metadata(raw_author, raw_title)
        return artist

    @property
    def media_content_id(self) -> str | None:
        """Stream URI when known."""
        np = _now_playing(self.coordinator.data)
        if not np:
            return None
        return np.get("uri")

    @property
    def media_duration(self) -> int | None:
        """Duration in seconds (Red reports ms)."""
        np = _now_playing(self.coordinator.data)
        if not np:
            return None
        length = np.get("length")
        if length is None:
            return None
        try:
            ms = int(length)
        except (TypeError, ValueError):
            return None
        return max(0, ms // 1000)

    @property
    def media_position(self) -> int | None:
        """Current playback position in seconds from Red queue payload."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        pos = data.get("position_ms")
        if pos is None:
            return None
        try:
            ms = int(pos)
        except (TypeError, ValueError):
            return None
        return max(0, ms // 1000)

    @property
    def media_position_updated_at(self):
        """Timestamp for the latest position sample."""
        if self.media_position is None:
            return None
        # Position comes from periodic queue polling.
        return self.coordinator.last_queue_poll_utc

    @property
    def media_image_url(self) -> str | None:
        """Album / track art from TheAudioDB when metadata matches."""
        return self.coordinator.media_image_url

    @property
    def media_image_remotely_accessible(self) -> bool:
        """TheAudioDB CDN URLs do not need local proxying."""
        return self.coordinator.media_image_url is not None

    @property
    def volume_level(self) -> float | None:
        """Lavalink / Audio guild volume as 0..1."""
        data = self.coordinator.data
        if not isinstance(data, dict) or "volume_percent" not in data:
            return None
        vp = data.get("volume_percent")
        if vp is None:
            return None
        try:
            pct = float(vp)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, pct / 100.0))

    @property
    def is_volume_muted(self) -> bool | None:
        """True when Audio volume is at/below the mute sentinel."""
        vol = self.volume_level
        if vol is None:
            return None
        return vol <= _MUTED_VOLUME_LEVEL

    @property
    def shuffle(self) -> bool | None:
        """Red Audio shuffle setting."""
        data = self.coordinator.data
        if not isinstance(data, dict) or data.get("shuffle") is None:
            return None
        return bool(data["shuffle"])

    @property
    def repeat(self) -> RepeatMode | None:
        """Map Red boolean repeat to HA repeat modes."""
        data = self.coordinator.data
        if not isinstance(data, dict) or data.get("repeat") is None:
            return None
        return RepeatMode.ALL if data["repeat"] else RepeatMode.OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Queue length and Discord context for dashboards."""
        data = self.coordinator.data
        if not data or not isinstance(data, dict):
            return {}
        out: dict[str, Any] = {}
        np = data.get("now_playing")
        if isinstance(np, dict):
            if "title" in np and np["title"] is not None:
                out["red_media_title"] = str(np["title"])
            if "author" in np and np["author"] is not None:
                out["red_media_author"] = str(np["author"])
        if isinstance(data.get("queue"), list):
            out["queue_length"] = len(data["queue"])
        for key in (
            "guild_name",
            "voice_channel_name",
            "voice_channel_id",
            "bot_self_mute",
            "bot_self_deaf",
        ):
            if key in data and data[key] is not None:
                out[key] = data[key]
        return out

    async def async_media_play(self) -> None:
        """Resume if paused (Red pause toggles)."""
        if self.state != MediaPlayerState.PAUSED:
            return
        await self._rpc_pause()

    async def async_media_pause(self) -> None:
        """Pause if playing."""
        if self.state != MediaPlayerState.PLAYING:
            return
        await self._rpc_pause()

    async def async_media_play_pause(self) -> None:
        """Toggle pause (Red behavior)."""
        if self.state in (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED):
            await self._rpc_pause()

    async def async_media_stop(self) -> None:
        """Stop playback and clear queue ([p]stop)."""
        await self._rpc_actor_cmd("HAREDRPC__STOP", [])

    async def async_turn_on(self) -> None:
        """Join voice using summon."""
        await self._rpc_actor_cmd("HAREDRPC__SUMMON", [])

    async def async_turn_off(self) -> None:
        """Leave voice using disconnect."""
        await self._rpc_actor_cmd("HAREDRPC__DISCONNECT", [])

    async def async_media_next_track(self) -> None:
        """Skip current track ([p]skip)."""
        await self._rpc_actor_cmd("HAREDRPC__SKIP", [])

    async def async_media_previous_track(self) -> None:
        """Previous track ([p]previous)."""
        await self._rpc_actor_cmd("HAREDRPC__PREVIOUS", [])

    async def async_clear_playlist(self) -> None:
        """Clear queued tracks ([p]queue clear)."""
        await self._rpc_actor_cmd("HAREDRPC__QUEUE_CLEAR", [])

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume 0..1 as Audio percent."""
        pct = int(round(max(0.0, min(1.0, volume)) * 100))
        p = get_rpc_params(self._entry)
        try:
            result = await rpc_call(
                p["host"],
                p["port"],
                "HAREDRPC__VOLUME",
                [p["guild_id"], p["channel_id"], p["actor_id"], pct],
                timeout=90.0,
            )
            _raise_on_rpc_result_error("HAREDRPC__VOLUME", result)
        except RedRpcError as err:
            _LOGGER.error("volume failed: %s", err)
            raise HomeAssistantError(f"RedBot Media Player: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute (Red: 1% sentinel vs restored level)."""
        if mute:
            cur = self.volume_level
            if cur is not None and cur > _MUTED_VOLUME_LEVEL:
                self._restore_volume_level = cur
            # Red Audio may treat volume 0 as "show current volume" instead of setting.
            await self.async_set_volume_level(_MUTED_VOLUME_LEVEL)
            return
        target = self._restore_volume_level
        if target is None:
            target = 0.5
        await self.async_set_volume_level(target)
        self._restore_volume_level = None

    async def async_unmute_volume(self) -> None:
        """Restore volume after mute (legacy helper; prefer async_mute_volume(False))."""
        await self.async_mute_volume(False)

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Match Red shuffle setting; may toggle once."""
        cur = self.shuffle
        if cur is None:
            if not shuffle:
                return
        elif bool(cur) == bool(shuffle):
            return
        await self._rpc_actor_cmd("HAREDRPC__SHUFFLE", [])
        await self.coordinator.async_request_refresh()

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Match Red repeat; ALL/ONE treated as on, OFF as off."""
        want_on = repeat in (RepeatMode.ALL, RepeatMode.ONE)
        cur = self.repeat
        if cur is None:
            if not want_on:
                return
        else:
            is_on = cur in (RepeatMode.ALL, RepeatMode.ONE)
            if is_on == want_on:
                return
        await self._rpc_actor_cmd("HAREDRPC__REPEAT", [])
        await self.coordinator.async_request_refresh()

    async def async_media_seek(self, position: float) -> None:
        """Seek to absolute position by converting to Red relative seek."""
        target_seconds = max(0.0, position)
        duration = self.media_duration
        if duration is not None:
            target_seconds = min(target_seconds, float(duration))
        current_seconds = float(self.media_position or 0)
        delta_seconds = int(round(target_seconds - current_seconds))
        if delta_seconds == 0:
            return
        await self._rpc_actor_cmd("HAREDRPC__SEEK", [delta_seconds])
        # Red/Lavalink can report pre-seek position for a short moment; sample again
        # so the scrub bar catches up quickly instead of waiting for the next poll.
        await asyncio.sleep(0.75)
        await self.coordinator.async_request_refresh()

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Enqueue/play a query or URL (same as HAREDRPC__PLAY)."""
        p = get_rpc_params(self._entry)
        try:
            result = await rpc_call(
                p["host"],
                p["port"],
                "HAREDRPC__PLAY",
                [p["guild_id"], p["channel_id"], media_id, p["actor_id"]],
                timeout=180.0,
            )
            _raise_on_rpc_result_error("HAREDRPC__PLAY", result)
        except RedRpcError as err:
            _LOGGER.error("play_media failed: %s", err)
            raise HomeAssistantError(f"RedBot Media Player: {err}") from err
        await self.coordinator.async_request_refresh()

    async def _rpc_actor_cmd(self, method: str, extra: list[Any]) -> None:
        p = get_rpc_params(self._entry)
        params = [p["guild_id"], p["channel_id"], p["actor_id"], *extra]
        try:
            result = await rpc_call(
                p["host"],
                p["port"],
                method,
                params,
                timeout=120.0,
            )
            _raise_on_rpc_result_error(method, result)
        except RedRpcError as err:
            _LOGGER.error("%s failed: %s", method, err)
            raise HomeAssistantError(f"RedBot Media Player: {err}") from err
        await self.coordinator.async_request_refresh()

    async def _rpc_pause(self) -> None:
        p = get_rpc_params(self._entry)
        try:
            result = await rpc_call(
                p["host"],
                p["port"],
                "HAREDRPC__PAUSE",
                [p["guild_id"], p["channel_id"], p["actor_id"]],
                timeout=90.0,
            )
            _raise_on_rpc_result_error("HAREDRPC__PAUSE", result)
        except RedRpcError as err:
            _LOGGER.error("pause failed: %s", err)
            raise HomeAssistantError(f"RedBot Media Player: {err}") from err
        await self.coordinator.async_request_refresh()
