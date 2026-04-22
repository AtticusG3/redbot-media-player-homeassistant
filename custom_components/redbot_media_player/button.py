"""Dynamic playlist launcher buttons."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .helpers import device_info_for_red_entry, get_rpc_params
from .playlist_coordinator import RedRpcPlaylistCoordinator
from .rpc import RedRpcError, rpc_call

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamic playlist buttons from coordinator data."""
    playlist_coordinator: RedRpcPlaylistCoordinator = hass.data[DOMAIN][
        "playlist_coordinators"
    ][entry.entry_id]
    entities: dict[str, RedDiscordPlaylistButton] = {}

    def _normalized_playlists() -> list[dict[str, str]]:
        data = playlist_coordinator.data or {}
        raw = data.get("playlists", [])
        out: list[dict[str, str]] = []
        for item in raw:
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    continue
                out.append({"key": name.lower(), "name": name, "scope": "unknown"})
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            scope = str(item.get("scope") or "unknown").strip().lower() or "unknown"
            stable_id = str(item.get("id") or name).strip()
            out.append(
                {
                    "key": f"{scope}:{stable_id}",
                    "name": name,
                    "scope": scope,
                }
            )
        return out

    @callback
    def _sync_entities() -> None:
        current = {pl["key"]: pl for pl in _normalized_playlists()}
        new_entities: list[RedDiscordPlaylistButton] = []

        for key, pl in current.items():
            ent = entities.get(key)
            if ent is None:
                ent = RedDiscordPlaylistButton(playlist_coordinator, entry, pl)
                entities[key] = ent
                new_entities.append(ent)
            else:
                ent.update_playlist(pl)

        for key, ent in entities.items():
            ent.set_available(key in current and playlist_coordinator.last_update_success)

        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    remove_listener = playlist_coordinator.async_add_listener(_sync_entities)
    entry.async_on_unload(remove_listener)
    await playlist_coordinator.async_request_refresh()


class RedDiscordPlaylistButton(CoordinatorEntity[RedRpcPlaylistCoordinator], ButtonEntity):
    """Starts one specific playlist on press."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RedRpcPlaylistCoordinator,
        entry: ConfigEntry,
        playlist: dict[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._playlist_name = playlist["name"]
        self._scope = playlist["scope"]
        self._stable_key = playlist["key"]
        self._attr_unique_id = f"{entry.entry_id}_playlist_button_{self._stable_key}"
        self._attr_name = f"Start {self._playlist_name}"
        self._attr_available = coordinator.last_update_success

    def update_playlist(self, playlist: dict[str, str]) -> None:
        """Refresh display info for this playlist key."""
        self._playlist_name = playlist["name"]
        self._scope = playlist["scope"]
        self._attr_name = f"Start {self._playlist_name}"
        if self.hass is not None:
            self.async_write_ha_state()

    def set_available(self, is_available: bool) -> None:
        """Set availability when list changes."""
        self._attr_available = is_available
        if self.hass is not None:
            self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Same device as media player and diagnostics."""
        q_coord = self.hass.config_entries.async_get_entry(
            self._entry.entry_id
        ).runtime_data
        return device_info_for_red_entry(
            self._entry,
            data=q_coord.data if q_coord and q_coord.last_update_success else None,
            last_update_success=bool(q_coord and q_coord.last_update_success),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose playlist metadata for dashboards."""
        return {"playlist_name": self._playlist_name, "playlist_scope": self._scope}

    async def async_press(self) -> None:
        """Replace current playback with this saved playlist."""
        p = get_rpc_params(self._entry)
        try:
            stop_result = await rpc_call(
                p["host"],
                p["port"],
                "HAREDRPC__STOP",
                [p["guild_id"], p["channel_id"], p["actor_id"]],
                timeout=120.0,
            )
            if isinstance(stop_result, dict) and not stop_result.get("ok", True):
                detail = stop_result.get("detail")
                err = stop_result.get("error", "command_failed")
                if detail is None:
                    raise HomeAssistantError(f"RedBot Media Player stop failed: {err}")
                raise HomeAssistantError(
                    f"RedBot Media Player stop failed: {err} ({detail})"
                )

            start_result = await rpc_call(
                p["host"],
                p["port"],
                "HAREDRPC__PLAYLIST_START",
                [p["guild_id"], p["channel_id"], self._playlist_name, p["actor_id"]],
                timeout=300.0,
            )
        except RedRpcError as err:
            raise HomeAssistantError(f"RedBot Media Player: {err}") from err
        if isinstance(start_result, dict) and not start_result.get("ok", True):
            detail = start_result.get("detail")
            err = start_result.get("error", "command_failed")
            if detail is None:
                raise HomeAssistantError(f"RedBot Media Player playlist start failed: {err}")
            raise HomeAssistantError(
                f"RedBot Media Player playlist start failed: {err} ({detail})"
            )
        await self.coordinator.async_request_refresh()
