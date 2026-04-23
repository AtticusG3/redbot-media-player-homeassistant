"""Poll Red HAREDRPC__QUEUE for media_player state."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .audiodb import async_fetch_album_art_url, normalize_display_metadata
from .const import DOMAIN, FULL_HA_RED_RPC_METHODS, REPAIRS_ISSUE_RPC_UNAVAILABLE
from .helpers import get_audiodb_config, get_rpc_params
from .rpc import RedRpcError, rpc_call

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=15)


class RedRpcQueueCoordinator(DataUpdateCoordinator[dict | None]):
    """Fetches queue / now playing from Red."""

    config_entry: ConfigEntry
    rpc_method_names: frozenset[str] | None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.rpc_method_names = None
        self.media_image_url: str | None = None
        self._track_art_fingerprint: str | None = None
        self.last_queue_poll_utc = None
        self._repairs_issue_id = f"{REPAIRS_ISSUE_RPC_UNAVAILABLE}_{entry.entry_id}"

    @property
    def effective_rpc_methods(self) -> frozenset[str]:
        """Methods reported by Red (GET_METHODS), or full set if not probed (e.g. unit tests)."""
        if self.rpc_method_names is None:
            return FULL_HA_RED_RPC_METHODS
        return self.rpc_method_names

    async def _async_update_data(self) -> dict | None:
        p = get_rpc_params(self.config_entry)
        try:
            result = await rpc_call(
                p["host"],
                p["port"],
                "HAREDRPC__QUEUE",
                [p["guild_id"]],
                timeout=45.0,
            )
        except RedRpcError as err:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._repairs_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=REPAIRS_ISSUE_RPC_UNAVAILABLE,
                translation_placeholders={"host": str(p["host"]), "port": str(p["port"])},
            )
            raise UpdateFailed(f"Red RPC queue failed: {err}") from err
        if not isinstance(result, dict):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._repairs_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=REPAIRS_ISSUE_RPC_UNAVAILABLE,
                translation_placeholders={"host": str(p["host"]), "port": str(p["port"])},
            )
            raise UpdateFailed("Invalid queue response from Red")
        ir.async_delete_issue(self.hass, DOMAIN, self._repairs_issue_id)
        self.last_queue_poll_utc = dt_util.utcnow()
        await self._async_sync_audiodb_art(result)
        return result

    def _fingerprint_now_playing(self, data: dict) -> str | None:
        np = data.get("now_playing")
        if not isinstance(np, dict):
            return None
        title = str(np.get("title") or "")
        author = str(np.get("author") or "")
        uri = str(np.get("uri") or "")
        author, title = normalize_display_metadata(author, title)
        if not title and not author:
            return None
        return f"{author}\0{title}\0{uri}"

    async def _async_sync_audiodb_art(self, data: dict) -> None:
        """Update ``media_image_url`` when the current track changes."""
        fp = self._fingerprint_now_playing(data)
        if fp == self._track_art_fingerprint:
            return
        self._track_art_fingerprint = fp
        self.media_image_url = None
        if fp is None:
            return
        enabled, api_key = get_audiodb_config(self.config_entry)
        if not enabled:
            return
        np = data.get("now_playing")
        if not isinstance(np, dict):
            return
        try:
            self.media_image_url = await async_fetch_album_art_url(
                self.hass,
                api_key,
                str(np.get("author") or ""),
                str(np.get("title") or ""),
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.debug("TheAudioDB artwork lookup failed", exc_info=True)
            self.media_image_url = None
