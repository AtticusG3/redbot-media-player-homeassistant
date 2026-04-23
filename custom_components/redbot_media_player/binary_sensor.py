"""Diagnostic binary sensors from Red queue coordinator data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RedRpcQueueCoordinator
from .helpers import device_info_for_red_entry

PARALLEL_UPDATES = 1


def _rpc_poll_ok(coordinator: RedRpcQueueCoordinator) -> bool:
    """Last HAREDRPC__QUEUE poll completed (transport + JSON)."""
    return coordinator.last_update_success


def _audio_queue_ok(coordinator: RedRpcQueueCoordinator) -> bool:
    """Red returned ok for this guild (Audio loaded, etc.)."""
    if not coordinator.last_update_success:
        return False
    data = coordinator.data
    return isinstance(data, dict) and bool(data.get("ok"))


def _in_voice(coordinator: RedRpcQueueCoordinator) -> bool:
    """Bot has a Lavalink player voice channel for this guild."""
    if not coordinator.last_update_success:
        return False
    data = coordinator.data
    if not isinstance(data, dict) or not data.get("ok"):
        return False
    return data.get("voice_channel_id") is not None


@dataclass(frozen=True, kw_only=True)
class RedDiscordBinaryDescription(BinarySensorEntityDescription):
    """Binary diagnostic with value from coordinator."""

    value_fn: Callable[[RedRpcQueueCoordinator], bool]


BINARY_DESCRIPTIONS: tuple[RedDiscordBinaryDescription, ...] = (
    RedDiscordBinaryDescription(
        key="rpc_poll_ok",
        translation_key="rpc_poll_ok",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_rpc_poll_ok,
    ),
    RedDiscordBinaryDescription(
        key="audio_queue_ok",
        translation_key="audio_queue_ok",
        device_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_audio_queue_ok,
    ),
    RedDiscordBinaryDescription(
        key="in_voice",
        translation_key="in_voice",
        device_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_in_voice,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create diagnostic binary sensors for this config entry."""
    coordinator: RedRpcQueueCoordinator = entry.runtime_data
    async_add_entities(
        RedDiscordDiagnosticBinary(coordinator, entry, desc) for desc in BINARY_DESCRIPTIONS
    )


class RedDiscordDiagnosticBinary(
    CoordinatorEntity[RedRpcQueueCoordinator], BinarySensorEntity
):
    """Coordinator-backed diagnostic binary sensor."""

    entity_description: RedDiscordBinaryDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RedRpcQueueCoordinator,
        entry: ConfigEntry,
        description: RedDiscordBinaryDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_diagnostic_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True / False from coordinator snapshot."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Same device as the media player; name follows voice/guild when ok."""
        return device_info_for_red_entry(
            self._entry,
            data=self.coordinator.data if self.coordinator.last_update_success else None,
            last_update_success=self.coordinator.last_update_success,
        )
