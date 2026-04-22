"""Tests for WebSocket JSON-RPC client."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.redbot_media_player.const import LEGACY_HA_RED_RPC_METHODS
from custom_components.redbot_media_player.rpc import (
    RedRpcError,
    async_fetch_red_rpc_methods,
    rpc_call,
    verify_red_rpc,
)


class _ACM:
    """Async context manager helper."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *args: object) -> None:
        return None


def _text_msg(payload: dict) -> MagicMock:
    m = MagicMock()
    m.type = aiohttp.WSMsgType.TEXT
    m.data = json.dumps(payload)
    return m


class _FakeWS:
    def __init__(self, messages: list[MagicMock]) -> None:
        self._iter = iter(messages)

    async def send_str(self, _data: str) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[MagicMock]:
        return self

    async def __anext__(self) -> MagicMock:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_rpc_call_success() -> None:
    ws = _FakeWS([_text_msg({"jsonrpc": "2.0", "id": 1, "result": ["HAREDRPC__QUEUE"]})])
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))

    class _SessCM:
        async def __aenter__(self) -> MagicMock:
            return session

        async def __aexit__(self, *a: object) -> None:
            return None

    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_SessCM()):
        out = await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)
        assert out == ["HAREDRPC__QUEUE"]


@pytest.mark.asyncio
async def test_rpc_call_with_params() -> None:
    ws = _FakeWS([_text_msg({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})])
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    sess_cm = _ACM(session)

    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=sess_cm):
        out = await rpc_call("127.0.0.1", 6133, "X", [1, 2], timeout=5.0)
        assert out == {"ok": True}


@pytest.mark.asyncio
async def test_rpc_call_jsonrpc_error_non_dict_detail() -> None:
    ws = _FakeWS([_text_msg({"jsonrpc": "2.0", "id": 1, "error": "plain"})])
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        with pytest.raises(RedRpcError, match="plain"):
            await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)


@pytest.mark.asyncio
async def test_rpc_call_jsonrpc_error() -> None:
    ws = _FakeWS(
        [_text_msg({"jsonrpc": "2.0", "id": 1, "error": {"message": "bad"}})]
    )
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        with pytest.raises(RedRpcError, match="bad"):
            await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)


@pytest.mark.asyncio
async def test_rpc_call_skips_non_text_until_text_result() -> None:
    """Non-TEXT frames are ignored; loop continues until a matching TEXT response."""
    binary = MagicMock()
    binary.type = aiohttp.WSMsgType.BINARY
    ws = _FakeWS(
        [
            binary,
            _text_msg({"jsonrpc": "2.0", "id": 1, "result": "after-binary"}),
        ]
    )
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        out = await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)
        assert out == "after-binary"


@pytest.mark.asyncio
async def test_rpc_call_skips_wrong_id() -> None:
    ws = _FakeWS(
        [
            _text_msg({"jsonrpc": "2.0", "id": 99, "result": "ignore"}),
            _text_msg({"jsonrpc": "2.0", "id": 1, "result": "ok"}),
        ]
    )
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        out = await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)
        assert out == "ok"


@pytest.mark.asyncio
async def test_rpc_call_ws_error_message_breaks_loop() -> None:
    err = MagicMock()
    err.type = aiohttp.WSMsgType.ERROR
    ws = _FakeWS([err])
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        with pytest.raises(RedRpcError, match="No JSON-RPC result"):
            await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)


@pytest.mark.asyncio
async def test_rpc_call_no_messages_raises() -> None:
    """WebSocket yields nothing: loop exits and raises at end."""
    ws = _FakeWS([])
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        with pytest.raises(RedRpcError, match="No JSON-RPC result"):
            await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)


@pytest.mark.asyncio
async def test_rpc_call_closes_without_result() -> None:
    closed = MagicMock()
    closed.type = aiohttp.WSMsgType.CLOSED
    ws = _FakeWS([closed])
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=_ACM(ws))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        with pytest.raises(RedRpcError, match="No JSON-RPC result"):
            await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)


@pytest.mark.asyncio
async def test_rpc_call_connector_error() -> None:
    session = MagicMock()
    session.ws_connect = MagicMock(side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError()))
    with patch("custom_components.redbot_media_player.rpc.aiohttp.ClientSession", return_value=_ACM(session)):
        with pytest.raises(RedRpcError, match="Cannot open WebSocket"):
            await rpc_call("127.0.0.1", 6133, "GET_METHODS", None, timeout=5.0)


@pytest.mark.asyncio
async def test_test_connection_ok() -> None:
    calls: list[tuple[str, object | None]] = []

    async def fake(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> object:
        calls.append((method, params))
        if method == "GET_METHODS":
            return ["HAREDRPC__QUEUE"]
        if method == "HAREDRPC__QUEUE":
            return {"ok": True}
        raise AssertionError(method)

    with patch("custom_components.redbot_media_player.rpc.rpc_call", side_effect=fake):
        await verify_red_rpc("127.0.0.1", 6133, 42, timeout=5.0)
    assert calls[0][0] == "GET_METHODS"
    assert calls[1] == ("HAREDRPC__QUEUE", [42])


@pytest.mark.asyncio
async def test_test_connection_missing_queue_method() -> None:
    async def fake(*a: object, **k: object) -> list[str]:
        return ["OTHER"]

    with patch("custom_components.redbot_media_player.rpc.rpc_call", side_effect=fake):
        with pytest.raises(RedRpcError, match="HAREDRPC__QUEUE missing"):
            await verify_red_rpc("127.0.0.1", 6133, 1, timeout=5.0)


@pytest.mark.asyncio
async def test_test_connection_methods_not_list() -> None:
    async def fake(*a: object, **k: object) -> str:
        return "nope"

    with patch("custom_components.redbot_media_player.rpc.rpc_call", side_effect=fake):
        with pytest.raises(RedRpcError, match="HAREDRPC__QUEUE missing"):
            await verify_red_rpc("127.0.0.1", 6133, 1, timeout=5.0)


@pytest.mark.asyncio
async def test_async_fetch_red_rpc_methods_success() -> None:
    async def fake(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> object:
        assert method == "GET_METHODS"
        return ["HAREDRPC__QUEUE", "HAREDRPC__VOLUME"]

    with patch("custom_components.redbot_media_player.rpc.rpc_call", side_effect=fake):
        out = await async_fetch_red_rpc_methods("127.0.0.1", 6133, timeout=5.0)
    assert out == frozenset({"HAREDRPC__QUEUE", "HAREDRPC__VOLUME"})


@pytest.mark.asyncio
async def test_async_fetch_red_rpc_methods_error_falls_back_to_legacy() -> None:
    with patch(
        "custom_components.redbot_media_player.rpc.rpc_call",
        side_effect=RedRpcError("down"),
    ):
        out = await async_fetch_red_rpc_methods("127.0.0.1", 6133, timeout=5.0)
    assert out == LEGACY_HA_RED_RPC_METHODS


@pytest.mark.asyncio
async def test_async_fetch_red_rpc_methods_non_list_falls_back() -> None:
    async def fake(*a: object, **k: object) -> str:
        return "nope"

    with patch("custom_components.redbot_media_player.rpc.rpc_call", side_effect=fake):
        out = await async_fetch_red_rpc_methods("127.0.0.1", 6133, timeout=5.0)
    assert out == LEGACY_HA_RED_RPC_METHODS
