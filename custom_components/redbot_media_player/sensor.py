"""Diagnostic sensors from Red queue coordinator data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .audiodb import normalize_display_metadata
from .const import DOMAIN
from .coordinator import RedRpcQueueCoordinator
from .helpers import device_info_for_red_entry, get_rpc_params
from .playlist_coordinator import RedRpcPlaylistCoordinator

PARALLEL_UPDATES = 1


def _queue_length(coordinator: RedRpcQueueCoordinator) -> int | None:
    """Number of tracks queued after the current item."""
    if not coordinator.last_update_success:
        return None
    data = coordinator.data
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    q = data.get("queue")
    if not isinstance(q, list):
        return None
    return len(q)


def _queue_status(coordinator: RedRpcQueueCoordinator) -> str | None:
    """Red queue payload status token for automations and support."""
    if not coordinator.last_update_success:
        return "rpc_unavailable"
    data = coordinator.data
    if not isinstance(data, dict):
        return "invalid_response"
    if data.get("ok"):
        return "ok"
    err = data.get("error")
    return str(err) if err is not None else "unknown_error"


def _guild_id_sensor(coordinator: RedRpcQueueCoordinator) -> str | None:
    """Configured Discord guild snowflake (from HA config entry)."""
    return str(get_rpc_params(coordinator.config_entry)["guild_id"])


def _voice_channel_id(coordinator: RedRpcQueueCoordinator) -> str | None:
    """Voice channel id from Lavalink when connected, else none."""
    if not coordinator.last_update_success:
        return None
    data = coordinator.data
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    vid = data.get("voice_channel_id")
    if vid is None:
        return None
    return str(vid)


@dataclass(frozen=True, kw_only=True)
class RedDiscordSensorDescription(SensorEntityDescription):
    """Diagnostic sensor with value from coordinator or entry."""

    value_fn: Callable[[RedRpcQueueCoordinator], Any]


SENSOR_DESCRIPTIONS: tuple[RedDiscordSensorDescription, ...] = (
    RedDiscordSensorDescription(
        key="queue_length",
        translation_key="queue_length",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_queue_length,
    ),
    RedDiscordSensorDescription(
        key="queue_status",
        translation_key="queue_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_queue_status,
    ),
    RedDiscordSensorDescription(
        key="guild_id",
        translation_key="guild_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_guild_id_sensor,
    ),
    RedDiscordSensorDescription(
        key="voice_channel_id",
        translation_key="voice_channel_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_voice_channel_id,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create diagnostic sensors for this config entry."""
    coordinator: RedRpcQueueCoordinator = entry.runtime_data
    playlist_coordinator: RedRpcPlaylistCoordinator = hass.data[DOMAIN][
        "playlist_coordinators"
    ][entry.entry_id]
    queue_entities = [
        RedDiscordDiagnosticSensor(coordinator, entry, desc)
        for desc in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(
        [
            *queue_entities,
            RedDiscordQueueInventorySensor(coordinator, entry),
            RedDiscordPlaylistInventorySensor(playlist_coordinator, coordinator, entry),
        ]
    )


class RedDiscordDiagnosticSensor(CoordinatorEntity[RedRpcQueueCoordinator], SensorEntity):
    """Coordinator-backed diagnostic sensor."""

    entity_description: RedDiscordSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RedRpcQueueCoordinator,
        entry: ConfigEntry,
        description: RedDiscordSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_diagnostic_{description.key}"

    @property
    def native_value(self) -> int | str | None:
        """Value from coordinator snapshot."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Same device as the media player."""
        return device_info_for_red_entry(
            self._entry,
            data=self.coordinator.data if self.coordinator.last_update_success else None,
            last_update_success=self.coordinator.last_update_success,
        )


class RedDiscordPlaylistInventorySensor(
    CoordinatorEntity[RedRpcPlaylistCoordinator], SensorEntity
):
    """Playlist inventory snapshot with full list in attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "playlists_count"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        playlist_coordinator: RedRpcPlaylistCoordinator,
        queue_coordinator: RedRpcQueueCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(playlist_coordinator)
        self._entry = entry
        self._queue_coordinator = queue_coordinator
        self._attr_unique_id = f"{entry.entry_id}_diagnostic_playlists_count"

    @property
    def native_value(self) -> str | None:
        """Playlist count from the latest poll."""
        if not self.coordinator.last_update_success:
            return None
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        playlists = data.get("playlists", [])
        if not isinstance(playlists, list):
            return None
        return len(playlists)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose complete playlist metadata from Red."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return {}
        out: dict[str, Any] = {}
        playlists = data.get("playlists")
        if isinstance(playlists, list):
            out["playlists"] = playlists
        if "error" in data and data["error"] is not None:
            out["error"] = data["error"]
        return out

    @property
    def device_info(self) -> DeviceInfo:
        """Same device as media player."""
        return device_info_for_red_entry(
            self._entry,
            data=(
                self._queue_coordinator.data
                if self._queue_coordinator.last_update_success
                else None
            ),
            last_update_success=self._queue_coordinator.last_update_success,
        )


class RedDiscordQueueInventorySensor(
    CoordinatorEntity[RedRpcQueueCoordinator], SensorEntity
):
    """Queue snapshot with full queue payload in attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "queue_items"

    def __init__(
        self,
        queue_coordinator: RedRpcQueueCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(queue_coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_diagnostic_queue_items"

    @property
    def native_value(self) -> str | None:
        """Up-next display value as ``Artist - Title``."""
        if not self.coordinator.last_update_success:
            return None
        data = self.coordinator.data
        if not isinstance(data, dict) or not data.get("ok"):
            return None
        queue = data.get("queue")
        if not isinstance(queue, list) or not queue:
            return None
        first = queue[0]
        if not isinstance(first, dict):
            return None
        raw_title = str(first.get("title") or "")
        raw_author = str(first.get("author") or "")
        artist, title = normalize_display_metadata(raw_author, raw_title)
        if artist and title:
            return f"{artist} - {title}"
        if title:
            return title
        if artist:
            return artist
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose sanitized queue lines and selected now_playing fields."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return {}
        out: dict[str, Any] = {}
        queue = data.get("queue")
        if isinstance(queue, list):
            queue_lines: list[str] = []
            for item in queue:
                if not isinstance(item, dict):
                    continue
                raw_title = str(item.get("title") or "")
                raw_author = str(item.get("author") or "")
                artist, title = normalize_display_metadata(raw_author, raw_title)
                if artist and title:
                    queue_lines.append(f"{artist} - {title}")
                elif title:
                    queue_lines.append(title)
                elif artist:
                    queue_lines.append(artist)
            out["queue"] = queue_lines
            out["queue_count"] = len(queue_lines)
        np = data.get("now_playing")
        if isinstance(np, dict):
            out["now_playing"] = np
        if "error" in data and data["error"] is not None:
            out["error"] = data["error"]
        return out

    @property
    def device_info(self) -> DeviceInfo:
        """Same device as media player."""
        return device_info_for_red_entry(
            self._entry,
            data=self.coordinator.data if self.coordinator.last_update_success else None,
            last_update_success=self.coordinator.last_update_success,
        )
