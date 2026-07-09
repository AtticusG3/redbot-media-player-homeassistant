"""Poll Red HAREDRPC__PLAYLIST_LIST for saved playlist metadata."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE
from .helpers import (
    create_rpc_repairs_issue,
    delete_rpc_repairs_issue,
    get_rpc_params,
)
from .rpc import RedRpcError, rpc_call

_LOGGER = logging.getLogger(__name__)

PLAYLIST_SCAN_INTERVAL = timedelta(minutes=10)


class RedRpcPlaylistCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches saved playlist inventory from Red."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
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

    def _fail_playlist_update(
        self,
        host: str,
        port: int,
        message: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        """Record repairs issue and raise UpdateFailed."""
        create_rpc_repairs_issue(
            self.hass,
            issue_id=self._repairs_issue_id,
            translation_key=REPAIRS_ISSUE_PLAYLIST_RPC_UNAVAILABLE,
            host=host,
            port=port,
        )
        raise UpdateFailed(message) from cause

    async def _async_update_data(self) -> dict[str, Any]:
        p = get_rpc_params(self.config_entry)
        host = str(p["host"])
        port = p["port"]
        try:
            result = await rpc_call(
                p["host"],
                port,
                "HAREDRPC__PLAYLIST_LIST",
                [p["guild_id"], p["actor_id"]],
                timeout=90.0,
            )
        except RedRpcError as err:
            self._fail_playlist_update(
                host, port, f"Red RPC playlist list failed: {err}", cause=err
            )

        if not isinstance(result, dict):
            self._fail_playlist_update(host, port, "Invalid playlist list response from Red")

        playlists = result.get("playlists")
        if playlists is None:
            result["playlists"] = []
            delete_rpc_repairs_issue(self.hass, self._repairs_issue_id)
            return result
        if not isinstance(playlists, list):
            self._fail_playlist_update(host, port, "Invalid playlists payload from Red")
        delete_rpc_repairs_issue(self.hass, self._repairs_issue_id)
        return result
