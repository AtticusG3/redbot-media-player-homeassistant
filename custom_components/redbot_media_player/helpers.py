"""Shared helpers for RedBot Media Player."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_ACTOR_USER_ID,
    CONF_AUDIODB_API_KEY,
    CONF_AUDIODB_ENABLE,
    CONF_CHANNEL_ID,
    CONF_GUILD_ID,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from .audiodb import DEFAULT_AUDIODB_API_KEY


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
    return {
        "host": d[CONF_HOST],
        "port": int(d[CONF_PORT]),
        "guild_id": int(d[CONF_GUILD_ID]),
        "channel_id": int(d[CONF_CHANNEL_ID]),
        "actor_id": int(d[CONF_ACTOR_USER_ID]),
    }


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
