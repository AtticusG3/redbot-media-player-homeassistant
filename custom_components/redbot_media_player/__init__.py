"""The RedBot Media Player integration (Red-DiscordBot JSON-RPC over WebSocket)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ACTOR_USER_ID,
    SERVICE_BUMPPLAY,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_PLAYLIST_NAME,
    ATTR_PLAYLIST_URL,
    ATTR_QUERY,
    ATTR_SELF_DEAF,
    ATTR_SELF_MUTE,
    DOMAIN,
    SERVICE_DISCONNECT,
    SERVICE_ENQUEUE,
    SERVICE_PAUSE,
    SERVICE_PLAY,
    SERVICE_PLAYLIST_SAVE_START,
    SERVICE_PLAYLIST_START,
    SERVICE_QUEUE,
    SERVICE_SUMMON,
    SERVICE_VOICE_STATE,
)
from .coordinator import RedRpcQueueCoordinator
from .helpers import get_rpc_params
from .playlist_coordinator import RedRpcPlaylistCoordinator
from .rpc import RedRpcError, async_fetch_red_rpc_methods, rpc_call, set_rpc_hass

_LOGGER = logging.getLogger(__name__)

_SERVICES_FLAG = f"{DOMAIN}_services_registered"
_PLAYLIST_COORDINATORS = f"{DOMAIN}_playlist_coordinators"
_RPC_PLAYLIST_SAVE_START = "HAREDRPC__PLAYLIST_SAVE_START"
_RPC_PLAYLIST_SAVE_START_NAMED = "HAREDRPC__PLAYLIST_SAVE_START_NAMED"
_SPOTIFY_OEMBED_URL = "https://open.spotify.com/oembed?url={url}"
_YOUTUBE_OEMBED_URL = "https://www.youtube.com/oembed?format=json&url={url}"
_PLAYLIST_NAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")

SERVICE_BASE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_ACTOR_USER_ID): cv.string,
    }
)

SERVICE_PLAY_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {vol.Required(ATTR_QUERY): cv.string}
)

SERVICE_PLAYLIST_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {vol.Required(ATTR_PLAYLIST_NAME): cv.string}
)

SERVICE_PLAYLIST_SAVE_START_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {vol.Required(ATTR_PLAYLIST_URL): cv.string}
)

SERVICE_VOICE_STATE_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Optional(ATTR_SELF_MUTE, default=False): cv.boolean,
        vol.Optional(ATTR_SELF_DEAF, default=False): cv.boolean,
    }
)


def _sanitize_playlist_name(value: str) -> str:
    """Normalize fetched playlist titles before sending to RPC."""
    return _PLAYLIST_NAME_SANITIZE_RE.sub("", value).strip()


def _guess_name_from_url(playlist_url: str) -> str | None:
    """Best-effort fallback when source metadata endpoint is unavailable."""
    parsed = urlparse(playlist_url)
    host = parsed.netloc.lower()
    if "spotify.com" in host:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0].lower() == "playlist" and parts[1]:
            return f"Spotify Playlist {parts[1]}"
    if "youtube.com" in host or "youtu.be" in host:
        list_id = None
        for pair in parsed.query.split("&"):
            key, _, value = pair.partition("=")
            if key == "list" and value:
                list_id = unquote(value)
                break
        if list_id:
            return f"YouTube Playlist {list_id}"
    return None


async def _async_fetch_playlist_title_from_oembed(playlist_url: str) -> str | None:
    """Fetch playlist title directly from Spotify/YouTube oEmbed endpoints."""
    parsed = urlparse(playlist_url)
    host = parsed.netloc.lower()
    encoded = quote_plus(playlist_url)
    oembed_url: str | None = None
    if "spotify.com" in host:
        oembed_url = _SPOTIFY_OEMBED_URL.format(url=encoded)
    elif "youtube.com" in host or "youtu.be" in host:
        oembed_url = _YOUTUBE_OEMBED_URL.format(url=encoded)
    if oembed_url is None:
        return None

    timeout = aiohttp.ClientTimeout(total=8.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(oembed_url, allow_redirects=True) as response:
                if response.status != 200:
                    return None
                payload = json.loads(await response.text())
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return None

    title = payload.get("title")
    if not isinstance(title, str):
        return None
    cleaned = _sanitize_playlist_name(title)
    return cleaned or None


async def _async_resolve_playlist_name(playlist_url: str) -> str | None:
    """Resolve playlist name from provider metadata with URL fallback."""
    resolved = await _async_fetch_playlist_title_from_oembed(playlist_url)
    if resolved:
        return resolved
    guessed = _guess_name_from_url(playlist_url)
    if guessed is None:
        return None
    return _sanitize_playlist_name(guessed)


async def _async_get_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise HomeAssistantError("Invalid config_entry_id for redbot_media_player")
        return entry
    entries = hass.config_entries.async_entries(DOMAIN)
    if len(entries) == 1:
        return entries[0]
    if not entries:
        raise HomeAssistantError("No RedBot Media Player integration configured")
    raise HomeAssistantError(
        "Multiple redbot_media_player entries: set config_entry_id in service data"
    )


def _normalize_service_result(result: Any) -> dict[str, Any]:
    """Normalize RPC results to service response payloads."""
    return result if isinstance(result, dict) else {"result": result}


async def _async_call_service_rpc(
    entry: ConfigEntry,
    rpc_method: str,
    params: list[Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    """Call one RPC method and map transport errors to service response."""
    p = get_rpc_params(entry)
    try:
        result = await rpc_call(
            p["host"],
            p["port"],
            rpc_method,
            params,
            timeout=timeout,
        )
    except RedRpcError as err:
        _LOGGER.error("%s failed: %s", rpc_method, err)
        return {"ok": False, "error": str(err)}
    return _normalize_service_result(result)


def _extract_actor_id_from_queue(queue_payload: Any) -> int | None:
    """Select a user ID from queue payload member fields."""
    if not isinstance(queue_payload, dict):
        return None
    bot_id_raw = queue_payload.get("bot_user_id")
    bot_user_id = (
        int(bot_id_raw)
        if isinstance(bot_id_raw, (int, str)) and str(bot_id_raw).isdigit()
        else None
    )
    candidate_fields = (
        "voice_member_ids",
        "voice_channel_member_ids",
        "channel_member_ids",
        "member_ids",
    )
    for field_name in candidate_fields:
        raw = queue_payload.get(field_name)
        if not isinstance(raw, list):
            continue
        for member in raw:
            member_id: int | None = None
            if isinstance(member, int):
                member_id = member
            elif isinstance(member, str) and member.isdigit():
                member_id = int(member)
            elif isinstance(member, dict):
                for key in ("user_id", "member_id", "id"):
                    value = member.get(key)
                    if isinstance(value, int):
                        member_id = value
                        break
                    if isinstance(value, str) and value.isdigit():
                        member_id = int(value)
                        break
            if member_id is None:
                continue
            if bot_user_id is not None and member_id == bot_user_id:
                continue
            return member_id
    return None


async def _async_resolve_actor_id(entry: ConfigEntry, call: ServiceCall) -> int:
    """Resolve actor from service override, config, or live channel member list."""
    actor_override = call.data.get(ATTR_ACTOR_USER_ID)
    if actor_override is not None:
        actor_text = str(actor_override).strip()
        if actor_text:
            return int(actor_text)
    p = get_rpc_params(entry)
    actor_id = p["actor_id"]
    if actor_id is not None:
        return actor_id
    queue_result = await _async_call_service_rpc(
        entry,
        "HAREDRPC__QUEUE",
        [p["guild_id"]],
        timeout=60.0,
    )
    if not queue_result.get("ok"):
        raise HomeAssistantError(
            "Cannot auto-select actor_user_id; queue lookup failed. "
            "Set actor_user_id in the integration or service data."
        )
    actor_from_queue = _extract_actor_id_from_queue(queue_result)
    if actor_from_queue is None:
        raise HomeAssistantError(
            "Cannot auto-select actor_user_id; no voice member IDs were provided by Red RPC. "
            "Set actor_user_id in the integration or service data."
        )
    return actor_from_queue


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Legacy setup."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RedBot Media Player from a config entry."""
    set_rpc_hass(hass)
    coordinator = RedRpcQueueCoordinator(hass, entry)
    playlist_coordinator = RedRpcPlaylistCoordinator(hass, entry)
    p = get_rpc_params(entry)
    coordinator.rpc_method_names = await async_fetch_red_rpc_methods(
        p["host"], p["port"]
    )
    await coordinator.async_refresh()
    entry.runtime_data = coordinator
    hass.data.setdefault(_PLAYLIST_COORDINATORS, {})[entry.entry_id] = playlist_coordinator
    hass.data.setdefault(DOMAIN, {})["playlist_coordinators"] = hass.data[
        _PLAYLIST_COORDINATORS
    ]

    async def _on_options_update(_h: HomeAssistant, updated: ConfigEntry) -> None:
        coord: RedRpcQueueCoordinator | None = updated.runtime_data
        if coord is None:
            return
        coord._track_art_fingerprint = None  # noqa: SLF001
        coord.media_image_url = None
        await coord.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(_on_options_update))

    await hass.config_entries.async_forward_entry_setups(
        entry, ("media_player", "binary_sensor", "sensor", "button")
    )

    async def handle_play(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__PLAY",
            [p["guild_id"], p["channel_id"], call.data[ATTR_QUERY], actor_id],
            timeout=180.0,
        )

    async def handle_bumpplay(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__BUMPPLAY",
            [p["guild_id"], p["channel_id"], call.data[ATTR_QUERY], actor_id],
            timeout=180.0,
        )

    async def handle_enqueue(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__ENQUEUE",
            [p["guild_id"], p["channel_id"], call.data[ATTR_QUERY], actor_id],
            timeout=180.0,
        )

    async def handle_pause(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__PAUSE",
            [p["guild_id"], p["channel_id"], actor_id],
            timeout=90.0,
        )

    async def handle_queue(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__QUEUE",
            [p["guild_id"]],
            timeout=60.0,
        )

    async def handle_playlist_start(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        result = await _async_call_service_rpc(
            ent,
            "HAREDRPC__PLAYLIST_START",
            [
                p["guild_id"],
                p["channel_id"],
                call.data[ATTR_PLAYLIST_NAME],
                actor_id,
            ],
            timeout=300.0,
        )
        if isinstance(result, dict) and result.get("ok", True):
            playlist_coord = hass.data.get(_PLAYLIST_COORDINATORS, {}).get(ent.entry_id)
            if playlist_coord is not None:
                await playlist_coord.async_request_refresh()
        return result

    async def handle_playlist_save_start(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        playlist_url = call.data[ATTR_PLAYLIST_URL]
        playlist_name = await _async_resolve_playlist_name(playlist_url)
        coordinator: RedRpcQueueCoordinator | None = ent.runtime_data
        supports_named_rpc = bool(
            coordinator
            and coordinator.rpc_method_names
            and _RPC_PLAYLIST_SAVE_START_NAMED in coordinator.rpc_method_names
            and playlist_name
        )
        rpc_method = (
            _RPC_PLAYLIST_SAVE_START_NAMED if supports_named_rpc else _RPC_PLAYLIST_SAVE_START
        )
        if supports_named_rpc and playlist_name:
            params = [
                p["guild_id"],
                p["channel_id"],
                playlist_name,
                playlist_url,
                actor_id,
            ]
        else:
            params = [
                p["guild_id"],
                p["channel_id"],
                playlist_url,
                actor_id,
            ]
        result = await _async_call_service_rpc(
            ent,
            rpc_method,
            params,
            timeout=300.0,
        )
        if isinstance(result, dict) and result.get("ok", True):
            playlist_coord = hass.data.get(_PLAYLIST_COORDINATORS, {}).get(ent.entry_id)
            if playlist_coord is not None:
                await playlist_coord.async_request_refresh()
        return result

    async def handle_summon(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__SUMMON",
            [p["guild_id"], p["channel_id"], actor_id],
            timeout=120.0,
        )

    async def handle_disconnect(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        actor_id = await _async_resolve_actor_id(ent, call)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__DISCONNECT",
            [p["guild_id"], p["channel_id"], actor_id],
            timeout=120.0,
        )

    async def handle_voice_state(call: ServiceCall) -> dict[str, Any]:
        ent = await _async_get_entry(hass, call)
        p = get_rpc_params(ent)
        return await _async_call_service_rpc(
            ent,
            "HAREDRPC__VOICE_STATE",
            [
                p["guild_id"],
                call.data[ATTR_SELF_MUTE],
                call.data[ATTR_SELF_DEAF],
            ],
            timeout=60.0,
        )

    if not hass.data.get(_SERVICES_FLAG):
        hass.data[_SERVICES_FLAG] = True
        hass.services.async_register(
            DOMAIN,
            SERVICE_PLAY,
            handle_play,
            schema=SERVICE_PLAY_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_BUMPPLAY,
            handle_bumpplay,
            schema=SERVICE_PLAY_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_ENQUEUE,
            handle_enqueue,
            schema=SERVICE_PLAY_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_PAUSE,
            handle_pause,
            schema=SERVICE_BASE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_QUEUE,
            handle_queue,
            schema=SERVICE_BASE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_PLAYLIST_START,
            handle_playlist_start,
            schema=SERVICE_PLAYLIST_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_PLAYLIST_SAVE_START,
            handle_playlist_save_start,
            schema=SERVICE_PLAYLIST_SAVE_START_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_SUMMON,
            handle_summon,
            schema=SERVICE_BASE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_DISCONNECT,
            handle_disconnect,
            schema=SERVICE_BASE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_VOICE_STATE,
            handle_voice_state,
            schema=SERVICE_VOICE_STATE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry; remove services when no entries remain."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ("media_player", "binary_sensor", "sensor", "button")
    )
    if not unload_ok:
        return False

    coordinator: RedRpcQueueCoordinator | None = entry.runtime_data
    if coordinator is not None:
        await coordinator.async_shutdown()
        entry.runtime_data = None
    playlist_coordinator = hass.data.get(_PLAYLIST_COORDINATORS, {}).pop(
        entry.entry_id, None
    )
    if playlist_coordinator is not None:
        await playlist_coordinator.async_shutdown()

    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
    ]
    if not remaining:
        for svc in (
            SERVICE_PLAY,
            SERVICE_BUMPPLAY,
            SERVICE_ENQUEUE,
            SERVICE_PAUSE,
            SERVICE_QUEUE,
            SERVICE_PLAYLIST_START,
            SERVICE_PLAYLIST_SAVE_START,
            SERVICE_SUMMON,
            SERVICE_DISCONNECT,
            SERVICE_VOICE_STATE,
        ):
            hass.services.async_remove(DOMAIN, svc)
        hass.data.pop(_SERVICES_FLAG, None)
        set_rpc_hass(None)
    return True
