"""Tests for integration setup and services."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.redbot_media_player import (
    DOMAIN,
    _guess_name_from_url,
    _normalize_service_result,
    async_setup,
)
from custom_components.redbot_media_player.const import (
    ATTR_ACTOR_USER_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_PLAYLIST_NAME,
    ATTR_PLAYLIST_URL,
    ATTR_QUERY,
    ATTR_SELF_DEAF,
    ATTR_SELF_MUTE,
    CONF_AUDIODB_ENABLE,
    FULL_HA_RED_RPC_METHODS,
    SERVICE_BUMPPLAY,
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


def _entry_data() -> dict[str, object]:
    return {
        "host": "127.0.0.1",
        "port": 6133,
        "guild_id": "1",
        "channel_id": "2",
        "actor_user_id": "3",
    }


@pytest.fixture(autouse=True)
def mock_playlist_name_resolver() -> None:
    """Keep tests offline by default; explicit tests can override this patch."""
    with patch(
        "custom_components.redbot_media_player._async_resolve_playlist_name",
        AsyncMock(return_value=None),
    ):
        yield


@pytest.mark.asyncio
async def test_async_setup_returns_true(hass: HomeAssistant) -> None:
    assert await async_setup(hass, {}) is True


def test_normalize_service_result_wraps_scalars() -> None:
    """Service responses wrap non-dict RPC results consistently."""
    assert _normalize_service_result({"ok": True}) == {"ok": True}
    assert _normalize_service_result("plain") == {"result": "plain"}


def test_guess_name_from_url_provider_fallbacks() -> None:
    """Playlist URL fallback naming covers Spotify and YouTube formats."""
    assert (
        _guess_name_from_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
        == "Spotify Playlist 37i9dQZF1DXcBWIGoYBM5M"
    )
    assert (
        _guess_name_from_url("https://www.youtube.com/watch?v=abc123&list=PL1234")
        == "YouTube Playlist PL1234"
    )


@pytest.mark.asyncio
async def test_options_update_noop_when_runtime_data_missing(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    """Options listener returns early if runtime_data was cleared (line 96-97)."""
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entry.runtime_data = None
    hass.config_entries.async_update_entry(
        entry,
        options={CONF_AUDIODB_ENABLE: False},
    )
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_options_update_clears_art_fingerprint(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    """Changing integration options resets artwork state and refreshes the coordinator."""
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coord = entry.runtime_data
    coord._track_art_fingerprint = "fp"  # noqa: SLF001
    coord.media_image_url = "http://example.com/a.jpg"

    hass.config_entries.async_update_entry(
        entry,
        options={CONF_AUDIODB_ENABLE: False},
    )
    await hass.async_block_till_done()

    assert coord.media_image_url is None


@pytest.mark.asyncio
async def test_async_setup_entry_registers_services(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY,
        {ATTR_QUERY: "q"},
        blocking=True,
        return_response=True,
    )
    assert res["ok"] is True

    bump = await hass.services.async_call(
        DOMAIN,
        SERVICE_BUMPPLAY,
        {ATTR_QUERY: "play now"},
        blocking=True,
        return_response=True,
    )
    assert bump["ok"] is True

    res2 = await hass.services.async_call(
        DOMAIN,
        SERVICE_ENQUEUE,
        {ATTR_QUERY: "q2"},
        blocking=True,
        return_response=True,
    )
    assert res2["ok"] is True

    res3 = await hass.services.async_call(
        DOMAIN, SERVICE_PAUSE, {}, blocking=True, return_response=True
    )
    assert res3["ok"] is True

    res4 = await hass.services.async_call(
        DOMAIN, SERVICE_QUEUE, {}, blocking=True, return_response=True
    )
    assert isinstance(res4, dict)

    res5 = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAYLIST_START,
        {ATTR_PLAYLIST_NAME: "pl"},
        blocking=True,
        return_response=True,
    )
    assert res5["ok"] is True

    res6 = await hass.services.async_call(
        DOMAIN, SERVICE_SUMMON, {}, blocking=True, return_response=True
    )
    assert res6["ok"] is True

    res7 = await hass.services.async_call(
        DOMAIN, SERVICE_DISCONNECT, {}, blocking=True, return_response=True
    )
    assert res7["ok"] is True

    res8 = await hass.services.async_call(
        DOMAIN,
        SERVICE_VOICE_STATE,
        {ATTR_SELF_MUTE: True, ATTR_SELF_DEAF: False},
        blocking=True,
        return_response=True,
    )
    assert res8["ok"] is True

    res9 = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAYLIST_SAVE_START,
        {ATTR_PLAYLIST_URL: "https://open.spotify.com/playlist/abc"},
        blocking=True,
        return_response=True,
    )
    assert res9["ok"] is True


@pytest.mark.asyncio
async def test_service_play_red_rpc_error(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    from custom_components.redbot_media_player.rpc import RedRpcError

    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    mock_rpc_call.side_effect = RedRpcError("down")
    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY,
        {ATTR_QUERY: "q"},
        blocking=True,
        return_response=True,
    )
    assert res["ok"] is False
    assert "down" in res["error"]


@pytest.mark.asyncio
async def test_service_non_dict_result_wrapped(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def scalar(
        *a: object, **k: object
    ) -> str:  # noqa: ARG001
        return "plain"

    mock_rpc_call.side_effect = scalar
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY,
        {ATTR_QUERY: "q"},
        blocking=True,
        return_response=True,
    )
    assert res == {"result": "plain"}


@pytest.mark.asyncio
async def test_service_invalid_config_entry_id(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    with pytest.raises(HomeAssistantError, match="Invalid config_entry_id"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PLAY,
            {ATTR_QUERY: "q", ATTR_CONFIG_ENTRY_ID: "missing"},
            blocking=True,
        )


@pytest.mark.asyncio
async def test_service_no_entries_raises(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    real_entries = hass.config_entries.async_entries

    def fake_entries(domain: str) -> list:
        if domain == DOMAIN:
            return []
        return real_entries(domain)

    with patch.object(hass.config_entries, "async_entries", fake_entries):
        with pytest.raises(HomeAssistantError, match="No RedBot Media Player"):
            await hass.services.async_call(
                DOMAIN, SERVICE_PLAY, {ATTR_QUERY: "q"}, blocking=True
            )


@pytest.mark.asyncio
async def test_service_multiple_entries_requires_id(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    e1 = MockConfigEntry(
        domain=DOMAIN,
        title="A",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "10",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    e2 = MockConfigEntry(
        domain=DOMAIN,
        title="B",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "20",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    e1.add_to_hass(hass)
    e2.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e1.entry_id)
    await hass.async_block_till_done()
    assert e1.state is ConfigEntryState.LOADED
    assert e2.state is ConfigEntryState.LOADED

    with pytest.raises(HomeAssistantError, match="Multiple"):
        await hass.services.async_call(
            DOMAIN, SERVICE_PLAY, {ATTR_QUERY: "q"}, blocking=True
        )


@pytest.mark.asyncio
async def test_service_with_config_entry_id(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    e1 = MockConfigEntry(
        domain=DOMAIN,
        title="A",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "10",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    e2 = MockConfigEntry(
        domain=DOMAIN,
        title="B",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "20",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    e1.add_to_hass(hass)
    e2.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e1.entry_id)
    await hass.async_block_till_done()
    assert e1.state is ConfigEntryState.LOADED
    assert e2.state is ConfigEntryState.LOADED

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY,
        {ATTR_QUERY: "q", ATTR_CONFIG_ENTRY_ID: e2.entry_id},
        blocking=True,
        return_response=True,
    )
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_async_unload_entry(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.asyncio
async def test_async_unload_entry_platforms_fail(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=AsyncMock,
        return_value=False,
    ):
        ok = await hass.config_entries.async_unload(entry.entry_id)
    assert ok is False


@pytest.mark.asyncio
async def test_services_removed_when_last_entry_unloaded(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    e1 = MockConfigEntry(domain=DOMAIN, title="A", data=_entry_data())
    e2 = MockConfigEntry(
        domain=DOMAIN,
        title="B",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "99",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    e1.add_to_hass(hass)
    e2.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e1.entry_id)
    await hass.async_block_till_done()
    assert e1.state is ConfigEntryState.LOADED
    assert e2.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(e1.entry_id)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_QUEUE,
        {ATTR_CONFIG_ENTRY_ID: e2.entry_id},
        blocking=True,
        return_response=True,
    )

    assert await hass.config_entries.async_unload(e2.entry_id)
    assert not hass.services.has_service(DOMAIN, SERVICE_QUEUE)


@pytest.mark.asyncio
async def test_service_config_entry_id_wrong_domain(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    """Reject config_entry_id that points at another integration domain."""
    rpc_entry = MockConfigEntry(domain=DOMAIN, title="R", data=_entry_data())
    other = MockConfigEntry(domain="light", title="L", data={})
    rpc_entry.add_to_hass(hass)
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(rpc_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError, match="Invalid config_entry_id"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PLAY,
            {ATTR_QUERY: "q", ATTR_CONFIG_ENTRY_ID: other.entry_id},
            blocking=True,
        )


@pytest.mark.parametrize(
    "service,extra,fail_method",
    [
        (SERVICE_ENQUEUE, {ATTR_QUERY: "q"}, "HAREDRPC__ENQUEUE"),
        (SERVICE_BUMPPLAY, {ATTR_QUERY: "q"}, "HAREDRPC__BUMPPLAY"),
        (SERVICE_PAUSE, {}, "HAREDRPC__PAUSE"),
        (SERVICE_PLAYLIST_START, {ATTR_PLAYLIST_NAME: "pl"}, "HAREDRPC__PLAYLIST_START"),
        (
            SERVICE_PLAYLIST_SAVE_START,
            {ATTR_PLAYLIST_URL: "https://open.spotify.com/playlist/abc"},
            "HAREDRPC__PLAYLIST_SAVE_START",
        ),
        (SERVICE_SUMMON, {}, "HAREDRPC__SUMMON"),
        (SERVICE_DISCONNECT, {}, "HAREDRPC__DISCONNECT"),
        (
            SERVICE_VOICE_STATE,
            {ATTR_SELF_MUTE: True, ATTR_SELF_DEAF: False},
            "HAREDRPC__VOICE_STATE",
        ),
    ],
)
@pytest.mark.asyncio
async def test_service_red_rpc_error_other_handlers(
    hass: HomeAssistant,
    mock_rpc_call: object,
    service: str,
    extra: dict[str, object],
    fail_method: str,
) -> None:
    """Each service handler returns ok False when its RPC call fails."""
    from custom_components.redbot_media_player.rpc import RedRpcError

    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "GET_METHODS":
            return list(FULL_HA_RED_RPC_METHODS)
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": None,
                "queue": [],
            }
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        if method == fail_method:
            raise RedRpcError("svc-fail")
        if method in (
            "HAREDRPC__PLAY",
            "HAREDRPC__BUMPPLAY",
            "HAREDRPC__ENQUEUE",
            "HAREDRPC__PAUSE",
            "HAREDRPC__PLAYLIST_START",
            "HAREDRPC__PLAYLIST_SAVE_START",
            "HAREDRPC__SUMMON",
            "HAREDRPC__DISCONNECT",
            "HAREDRPC__VOICE_STATE",
        ):
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN, service, extra, blocking=True, return_response=True
    )
    assert res["ok"] is False
    assert "svc-fail" in res["error"]


@pytest.mark.asyncio
async def test_service_queue_red_rpc_error(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    """Queue service uses HAREDRPC__QUEUE; fail on second call (service)."""
    from custom_components.redbot_media_player.rpc import RedRpcError

    q_calls = 0

    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        nonlocal q_calls
        if method == "GET_METHODS":
            return list(FULL_HA_RED_RPC_METHODS)
        if method == "HAREDRPC__QUEUE":
            q_calls += 1
            if q_calls == 2:
                raise RedRpcError("queue-svc-fail")
            return {
                "ok": True,
                "paused": False,
                "now_playing": None,
                "queue": [],
            }
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    with patch(
        "custom_components.redbot_media_player.coordinator.SCAN_INTERVAL",
        timedelta(days=1),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN, SERVICE_QUEUE, {}, blocking=True, return_response=True
    )
    assert res["ok"] is False
    assert "queue-svc-fail" in res["error"]


@pytest.mark.asyncio
async def test_unload_skips_coordinator_shutdown_when_runtime_missing(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    """Unload succeeds if runtime_data was cleared unexpectedly."""
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data = None
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.asyncio
async def test_service_playlist_save_start_refreshes_playlist_coordinator(
    hass: HomeAssistant, mock_rpc_call: AsyncMock
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    playlist_coord = hass.data["redbot_media_player_playlist_coordinators"][entry.entry_id]
    playlist_coord.async_request_refresh = AsyncMock()  # type: ignore[assignment]

    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict | list[str]:
        if method == "GET_METHODS":
            return list(FULL_HA_RED_RPC_METHODS)
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "paused": False, "now_playing": None, "queue": []}
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        if method == "HAREDRPC__PLAYLIST_SAVE_START":
            return {"ok": True, "saved_name": "My List", "started": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAYLIST_SAVE_START,
        {ATTR_PLAYLIST_URL: "https://open.spotify.com/playlist/abc"},
        blocking=True,
        return_response=True,
    )
    assert res["ok"] is True
    assert playlist_coord.async_request_refresh.await_count == 1


@pytest.mark.asyncio
async def test_service_playlist_save_start_uses_named_rpc_when_supported(
    hass: HomeAssistant, mock_rpc_call: AsyncMock
) -> None:
    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict | list[str]:
        if method == "GET_METHODS":
            return [*FULL_HA_RED_RPC_METHODS, "HAREDRPC__PLAYLIST_SAVE_START_NAMED"]
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "paused": False, "now_playing": None, "queue": []}
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        if method == "HAREDRPC__PLAYLIST_SAVE_START_NAMED":
            assert params == [1, 2, "AussieBBQ", "https://open.spotify.com/playlist/abc", 3]
            return {"ok": True, "saved_name": "AussieBBQ", "started": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with patch(
        "custom_components.redbot_media_player._async_resolve_playlist_name",
        AsyncMock(return_value="AussieBBQ"),
    ):
        res = await hass.services.async_call(
            DOMAIN,
            SERVICE_PLAYLIST_SAVE_START,
            {ATTR_PLAYLIST_URL: "https://open.spotify.com/playlist/abc"},
            blocking=True,
            return_response=True,
        )
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_service_playlist_save_start_falls_back_when_name_unresolved(
    hass: HomeAssistant, mock_rpc_call: AsyncMock
) -> None:
    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict | list[str]:
        if method == "GET_METHODS":
            return [*FULL_HA_RED_RPC_METHODS, "HAREDRPC__PLAYLIST_SAVE_START_NAMED"]
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "paused": False, "now_playing": None, "queue": []}
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        if method == "HAREDRPC__PLAYLIST_SAVE_START":
            assert params == [1, 2, "https://open.spotify.com/playlist/abc", 3]
            return {"ok": True, "saved_name": "Fallback", "started": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    entry = MockConfigEntry(domain=DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAYLIST_SAVE_START,
        {ATTR_PLAYLIST_URL: "https://open.spotify.com/playlist/abc"},
        blocking=True,
        return_response=True,
    )
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_service_play_auto_selects_actor_from_queue_members(
    hass: HomeAssistant, mock_rpc_call: AsyncMock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="T",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict | list[str]:
        if method == "GET_METHODS":
            return list(FULL_HA_RED_RPC_METHODS)
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "queue": [],
                "voice_member_ids": [4444, 5555],
                "bot_user_id": 5555,
            }
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        if method == "HAREDRPC__PLAY":
            assert params == [1, 2, "q", 4444]
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY,
        {ATTR_QUERY: "q"},
        blocking=True,
        return_response=True,
    )
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_service_play_auto_select_actor_missing_members_raises(
    hass: HomeAssistant, mock_rpc_call: AsyncMock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="T",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict | list[str]:
        if method == "GET_METHODS":
            return list(FULL_HA_RED_RPC_METHODS)
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "queue": []}
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    with pytest.raises(HomeAssistantError, match="Cannot auto-select actor_user_id"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PLAY,
            {ATTR_QUERY: "q"},
            blocking=True,
        )


@pytest.mark.asyncio
async def test_service_play_service_actor_override_wins(
    hass: HomeAssistant, mock_rpc_call: AsyncMock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="T",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def route(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict | list[str]:
        if method == "GET_METHODS":
            return list(FULL_HA_RED_RPC_METHODS)
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "queue": []}
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        if method == "HAREDRPC__PLAY":
            assert params == [1, 2, "q", 7777]
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = route
    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY,
        {ATTR_QUERY: "q", ATTR_ACTOR_USER_ID: "7777"},
        blocking=True,
        return_response=True,
    )
    assert res["ok"] is True
