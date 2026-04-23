"""Diagnostics support for RedBot Media Player."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_REDACT_KEYS = {
    "host",
    "port",
    "guild_id",
    "channel_id",
    "actor_user_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    queue_coordinator = entry.runtime_data
    playlist_coordinator = hass.data.get(DOMAIN, {}).get("playlist_coordinators", {}).get(
        entry.entry_id
    )
    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), _REDACT_KEYS),
            "options": async_redact_data(dict(entry.options), {"audiodb_api_key"}),
        },
        "queue": {
            "last_update_success": (
                bool(queue_coordinator and queue_coordinator.last_update_success)
            ),
            "data": async_redact_data(
                (
                    dict(queue_coordinator.data)
                    if queue_coordinator and isinstance(queue_coordinator.data, dict)
                    else {}
                ),
                _REDACT_KEYS,
            ),
        },
        "playlists": {
            "last_update_success": (
                bool(playlist_coordinator and playlist_coordinator.last_update_success)
            ),
            "data": async_redact_data(
                (
                    dict(playlist_coordinator.data)
                    if playlist_coordinator and isinstance(playlist_coordinator.data, dict)
                    else {}
                ),
                _REDACT_KEYS,
            ),
        },
    }
