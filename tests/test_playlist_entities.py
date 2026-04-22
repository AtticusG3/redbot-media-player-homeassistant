"""Tests for playlist coordinator and dynamic button entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.redbot_media_player import DOMAIN as RPC_DOMAIN
from custom_components.redbot_media_player.button import (
    RedDiscordPlaylistButton,
    async_setup_entry as async_setup_button_entry,
)
from custom_components.redbot_media_player.const import DOMAIN
from custom_components.redbot_media_player.playlist_coordinator import (
    RedRpcPlaylistCoordinator,
)
from custom_components.redbot_media_player.rpc import RedRpcError


def _entry_data() -> dict[str, object]:
    return {
        "host": "127.0.0.1",
        "port": 6133,
        "guild_id": "1",
        "channel_id": "2",
        "actor_user_id": "3",
    }


@pytest.mark.asyncio
async def test_playlist_button_setup_normalizes_and_updates(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)

    queue_runtime = type("QueueRuntime", (), {"last_update_success": True, "data": {"ok": True}})()
    entry.runtime_data = queue_runtime

    coord = RedRpcPlaylistCoordinator(hass, entry)
    coord.data = {
        "playlists": [
            "  SummerHits  ",
            {"name": "Road Trip", "scope": "guild", "id": "rt"},
            {"name": "  ", "scope": "guild", "id": "blank"},
            123,
        ]
    }
    coord.last_update_success = True

    hass.data.setdefault(DOMAIN, {})["playlist_coordinators"] = {entry.entry_id: coord}
    monkeypatch.setattr(coord, "async_request_refresh", AsyncMock())

    added: list[RedDiscordPlaylistButton] = []

    def _add_entities(entities) -> None:  # type: ignore[no-untyped-def]
        added.extend(list(entities))

    try:
        await async_setup_button_entry(hass, entry, _add_entities)

        assert len(added) == 2
        by_name = {e.extra_state_attributes["playlist_name"]: e for e in added}
        assert "SummerHits" in by_name
        assert "Road Trip" in by_name
        assert by_name["SummerHits"].extra_state_attributes["playlist_scope"] == "unknown"
        assert by_name["Road Trip"].extra_state_attributes["playlist_scope"] == "guild"
    finally:
        await coord.async_shutdown()


@pytest.mark.asyncio
async def test_playlist_button_press_and_errors(
    hass: HomeAssistant, mock_rpc_call: AsyncMock
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    queue_runtime = type("QueueRuntime", (), {"last_update_success": True, "data": {"ok": True}})()
    entry.runtime_data = queue_runtime

    coord = RedRpcPlaylistCoordinator(hass, entry)
    coord.last_update_success = True
    coord.data = {"playlists": []}
    coord.async_request_refresh = AsyncMock()  # type: ignore[assignment]

    ent = RedDiscordPlaylistButton(
        coord,
        entry,
        {"key": "guild:summer", "name": "Summer", "scope": "guild"},
    )
    ent.hass = hass

    # Success path
    await ent.async_press()
    assert coord.async_request_refresh.await_count == 1
    methods = [c[0][2] for c in mock_rpc_call.await_args_list]
    assert "HAREDRPC__STOP" in methods
    assert "HAREDRPC__PLAYLIST_START" in methods

    # Structured command failure without detail
    async def fail_no_detail(*_a, **_k):  # type: ignore[no-untyped-def]
        return {"ok": False, "error": "bad_playlist"}

    mock_rpc_call.side_effect = fail_no_detail
    with pytest.raises(HomeAssistantError, match="bad_playlist"):
        await ent.async_press()

    # Structured command failure with detail
    async def fail_with_detail(*_a, **_k):  # type: ignore[no-untyped-def]
        return {"ok": False, "error": "bad_playlist", "detail": "no access"}

    mock_rpc_call.side_effect = fail_with_detail
    with pytest.raises(HomeAssistantError, match="no access"):
        await ent.async_press()

    # Transport failure
    mock_rpc_call.side_effect = RedRpcError("offline")
    with pytest.raises(HomeAssistantError, match="offline"):
        await ent.async_press()

    # Device info branch with queue runtime data.
    dev = ent.device_info
    assert dev is not None


@pytest.mark.asyncio
async def test_playlist_button_update_and_available_without_hass(
    hass: HomeAssistant,
) -> None:
    """State mutation helpers should not require an attached HA entity."""
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcPlaylistCoordinator(hass, entry)
    ent = RedDiscordPlaylistButton(
        coord,
        entry,
        {"key": "guild:k", "name": "Initial", "scope": "guild"},
    )
    ent.update_playlist({"key": "guild:k", "name": "Changed", "scope": "user"})
    assert ent.extra_state_attributes["playlist_name"] == "Changed"
    assert ent.extra_state_attributes["playlist_scope"] == "user"
    ent.set_available(False)
    assert ent._attr_available is False  # noqa: SLF001
    await coord.async_shutdown()
