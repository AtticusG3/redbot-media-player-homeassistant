"""Shared helpers for RedBot Media Player."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .audiodb import DEFAULT_AUDIODB_API_KEY, normalize_display_metadata
from .const import (
    CONF_ACTOR_USER_ID,
    CONF_AUDIODB_API_KEY,
    CONF_AUDIODB_ENABLE,
    CONF_CHANNEL_ID,
    CONF_GUILD_ID,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    PLAYLIST_COORDINATORS_KEY,
)


def get_audiodb_config(entry: ConfigEntry) -> tuple[bool, str]:
    """Whether to use TheAudioDB and the v1 API key (from options)."""
    opts = entry.options
    enabled = bool(opts.get(CONF_AUDIODB_ENABLE, True))
    key = opts.get(CONF_AUDIODB_API_KEY)
    if key is None or (isinstance(key, str) and not key.strip()):
        key = DEFAULT_AUDIODB_API_KEY
    elif isinstance(key, str):
        key = key.strip()
    else:
        key = str(key)
    return enabled, key


def get_rpc_params(entry: ConfigEntry) -> dict[str, Any]:
    """Host, port, and Discord IDs from a config entry."""
    d = entry.data
    actor_raw = d.get(CONF_ACTOR_USER_ID)
    actor_id: int | None = None
    if actor_raw is not None:
        actor_text = str(actor_raw).strip()
        if actor_text:
            actor_id = int(actor_text)
    return {
        "host": d[CONF_HOST],
        "port": int(d[CONF_PORT]),
        "guild_id": int(d[CONF_GUILD_ID]),
        "channel_id": int(d[CONF_CHANNEL_ID]),
        "actor_id": actor_id,
    }


def get_playlist_coordinator(
    hass: HomeAssistant, entry_id: str
) -> DataUpdateCoordinator[dict[str, Any]] | None:
    """Return the playlist coordinator for a config entry, if loaded."""
    return hass.data.get(PLAYLIST_COORDINATORS_KEY, {}).get(entry_id)


def device_info_for_red_entry(
    entry: ConfigEntry,
    *,
    data: dict[str, Any] | None,
    last_update_success: bool,
) -> DeviceInfo:
    """Device block shared by media player and diagnostic entities."""
    name = entry.title
    if last_update_success and isinstance(data, dict) and data.get("ok"):
        vc = data.get("voice_channel_name")
        gn = data.get("guild_name")
        if vc:
            name = str(vc)
        elif gn:
            name = str(gn)
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=name,
        manufacturer="Red-DiscordBot",
        model="Audio (RPC)",
    )


def device_info_from_queue_coordinator(
    entry: ConfigEntry,
    coordinator: DataUpdateCoordinator[dict[str, Any] | None],
) -> DeviceInfo:
    """Device info using queue coordinator poll state."""
    return device_info_for_red_entry(
        entry,
        data=coordinator.data if coordinator.last_update_success else None,
        last_update_success=coordinator.last_update_success,
    )


def format_track_line(author: str, title: str) -> str | None:
    """Display ``Artist - Title`` from raw Lavalink author/title fields."""
    artist, track = normalize_display_metadata(author, title)
    if artist and track:
        return f"{artist} - {track}"
    if track:
        return track
    if artist:
        return artist
    return None


def raise_on_rpc_command_failure(label: str, result: Any) -> None:
    """Raise when an RPC command returns a structured command failure."""
    if not isinstance(result, dict):
        return
    if result.get("ok", True):
        return
    detail = result.get("detail")
    err = result.get("error", "command_failed")
    if detail is None:
        raise HomeAssistantError(f"RedBot Media Player {label} failed: {err}")
    raise HomeAssistantError(f"RedBot Media Player {label} failed: {err} ({detail})")


def create_rpc_repairs_issue(
    hass: HomeAssistant,
    *,
    issue_id: str,
    translation_key: str,
    host: str,
    port: int,
) -> None:
    """Create or refresh an RPC availability repairs issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=translation_key,
        translation_placeholders={"host": str(host), "port": str(port)},
    )


def delete_rpc_repairs_issue(hass: HomeAssistant, issue_id: str) -> None:
    """Clear an RPC availability repairs issue."""
    ir.async_delete_issue(hass, DOMAIN, issue_id)
