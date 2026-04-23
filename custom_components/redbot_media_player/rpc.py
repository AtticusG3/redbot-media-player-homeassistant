"""WebSocket JSON-RPC client for Red-DiscordBot (aiohttp only, no extra deps)."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import LEGACY_HA_RED_RPC_METHODS

_LOGGER = logging.getLogger(__name__)
_HASS_FOR_RPC_SESSION: HomeAssistant | None = None


class RedRpcError(Exception):
    """RPC call failed."""


_CONN_HINT = (
    "Cannot open WebSocket to Red RPC. Red listens on 127.0.0.1 only, so use host "
    "127.0.0.1 when Home Assistant runs on the same machine as Red (or host network / "
    "host.docker.internal from a container). The LAN IP (e.g. 192.168.x.x) will refuse "
    "unless you add a local proxy."
)


def set_rpc_hass(hass: HomeAssistant | None) -> None:
    """Set Home Assistant instance used for managed web sessions."""
    global _HASS_FOR_RPC_SESSION
    _HASS_FOR_RPC_SESSION = hass


async def rpc_call(
    host: str,
    port: int,
    method: str,
    params: list[Any] | None = None,
    *,
    timeout: float = 120.0,
) -> Any:
    """Call a Red RPC method over WebSocket JSON-RPC 2.0."""
    url = f"ws://{host}:{port}/"
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    session: aiohttp.ClientSession | None = None
    if _HASS_FOR_RPC_SESSION is not None:
        try:
            session = async_get_clientsession(_HASS_FOR_RPC_SESSION)
        except RuntimeError:
            # Some test and Windows loop combinations cannot construct HA's
            # default async resolver; fall back to the local threaded resolver.
            session = None

    if session is not None:
        try:
            return await _async_rpc_call_on_session(
                session, url, method, params
            )
        except RedRpcError:
            raise
        except (
            aiohttp.ClientConnectorError,
            aiohttp.ClientError,
            OSError,
            TimeoutError,
        ) as exc:
            raise RedRpcError(_CONN_HINT) from exc

    # Force threaded DNS resolver so Windows does not require aiodns SelectorEventLoop.
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(timeout=client_timeout, connector=connector) as owned:
        try:
            return await _async_rpc_call_on_session(
                owned, url, method, params
            )
        except RedRpcError:
            raise
        except (
            aiohttp.ClientConnectorError,
            aiohttp.ClientError,
            OSError,
            TimeoutError,
        ) as exc:
            raise RedRpcError(_CONN_HINT) from exc


async def _async_rpc_call_on_session(
    session: aiohttp.ClientSession,
    url: str,
    method: str,
    params: list[Any] | None,
) -> Any:
    """Send one JSON-RPC call over an existing aiohttp session."""
    async with session.ws_connect(url) as ws:
        msg_id = 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "id": msg_id,
        }
        if params is not None:
            payload["params"] = params
        await ws.send_str(json.dumps(payload))

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("id") != msg_id:
                    continue
                if "error" in data:
                    err = data["error"]
                    detail = err.get("message", err) if isinstance(err, dict) else err
                    raise RedRpcError(str(detail))
                return data.get("result")
            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    raise RedRpcError("No JSON-RPC result from Red")


async def async_fetch_red_rpc_methods(
    host: str, port: int, *, timeout: float = 15.0
) -> frozenset[str]:
    """Return method names from Red GET_METHODS, or a legacy set if the call fails."""
    try:
        raw = await rpc_call(host, port, "GET_METHODS", None, timeout=timeout)
    except RedRpcError:
        return LEGACY_HA_RED_RPC_METHODS
    if not isinstance(raw, list):
        return LEGACY_HA_RED_RPC_METHODS
    return frozenset(str(x) for x in raw)


async def verify_red_rpc(host: str, port: int, guild_id: int, timeout: float = 15.0) -> None:
    """Verify RPC and cog by listing methods and calling HAREDRPC__QUEUE."""
    methods = await rpc_call(host, port, "GET_METHODS", None, timeout=timeout)
    if not isinstance(methods, list) or "HAREDRPC__QUEUE" not in methods:
        raise RedRpcError("HAREDRPC__QUEUE missing; load ha_red_rpc on Red and restart with --rpc")
    await rpc_call(host, port, "HAREDRPC__QUEUE", [guild_id], timeout=timeout)
