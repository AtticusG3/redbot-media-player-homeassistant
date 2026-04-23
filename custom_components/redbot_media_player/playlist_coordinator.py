"""Poll Red HAREDRPC__PLAYLIST_LIST for saved playlist metadata."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE
from .helpers import get_rpc_params
from .rpc import RedRpcError, rpc_call

_LOGGER = logging.getLogger(__name__)

PLAYLIST_SCAN_INTERVAL = timedelta(minutes=10)


class RedRpcPlaylistCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches saved playlist inventory from Red."""

    config_entry: ConfigEntry

    def __init__(self, hass, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}_playlists",
            update_interval=PLAYLIST_SCAN_INTERVAL,
        )
        self._repairs_issue_id = (
            f"{REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE}_{entry.entry_id}"
        )

    async def _async_update_data(self) -> dict[str, Any]:
        p = get_rpc_params(self.config_entry)
        try:
            result = await rpc_call(
                p["host"],
                p["port"],
                "HAREDRPC__PLAYLIST_LIST",
                [p["guild_id"], p["actor_id"]],
                timeout=90.0,
            )
        except RedRpcError as err:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._repairs_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE,
                translation_placeholders={"host": str(p["host"]), "port": str(p["port"])},
            )
            raise UpdateFailed(f"Red RPC playlist list failed: {err}") from err

        if not isinstance(result, dict):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._repairs_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE,
                translation_placeholders={"host": str(p["host"]), "port": str(p["port"])},
            )
            raise UpdateFailed("Invalid playlist list response from Red")

        playlists = result.get("playlists")
        if playlists is None:
            result["playlists"] = []
            return result
        if not isinstance(playlists, list):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._repairs_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE,
                translation_placeholders={"host": str(p["host"]), "port": str(p["port"])},
            )
            raise UpdateFailed("Invalid playlists payload from Red")
        ir.async_delete_issue(self.hass, DOMAIN, self._repairs_issue_id)
        return result
