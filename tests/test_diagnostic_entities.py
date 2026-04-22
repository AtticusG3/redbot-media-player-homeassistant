"""Tests for diagnostic binary_sensor and sensor platforms."""

from __future__ import annotations

import pytest
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.redbot_media_player.binary_sensor import (
    BINARY_DESCRIPTIONS,
    RedDiscordDiagnosticBinary,
)
from custom_components.redbot_media_player.const import DOMAIN as RPC_DOMAIN
from custom_components.redbot_media_player.coordinator import RedRpcQueueCoordinator
from custom_components.redbot_media_player.playlist_coordinator import RedRpcPlaylistCoordinator
from custom_components.redbot_media_player.sensor import (
    RedDiscordPlaylistInventorySensor,
    RedDiscordQueueInventorySensor,
    SENSOR_DESCRIPTIONS,
    RedDiscordDiagnosticSensor,
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
async def test_diagnostic_entities_registered_disabled_by_default(
    hass: HomeAssistant,
    mock_rpc_call: object,
    entity_registry: er.EntityRegistry,
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    eid = entity_registry.async_get_entity_id(
        BINARY_SENSOR_DOMAIN, RPC_DOMAIN, f"{entry.entry_id}_diagnostic_rpc_poll_ok"
    )
    assert eid is not None
    reg = entity_registry.async_get(eid)
    assert reg is not None
    assert reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.asyncio
async def test_binary_sensor_values_from_coordinator(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    for desc in BINARY_DESCRIPTIONS:
        ent = RedDiscordDiagnosticBinary(coord, entry, desc)
        assert ent.is_on is desc.value_fn(coord)


@pytest.mark.asyncio
async def test_binary_sensors_off_when_poll_fails(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def fail(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            raise RedRpcError("down")
        raise AssertionError(method)

    mock_rpc_call.side_effect = fail
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    for desc in BINARY_DESCRIPTIONS:
        ent = RedDiscordDiagnosticBinary(coord, entry, desc)
        assert ent.is_on is False


@pytest.mark.asyncio
async def test_binary_audio_queue_ok_false(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def not_ok(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {"ok": False, "error": "audio_cog_not_loaded"}
        raise AssertionError(method)

    mock_rpc_call.side_effect = not_ok
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    poll_ent = RedDiscordDiagnosticBinary(
        coord, entry, next(d for d in BINARY_DESCRIPTIONS if d.key == "rpc_poll_ok")
    )
    audio_ent = RedDiscordDiagnosticBinary(
        coord, entry, next(d for d in BINARY_DESCRIPTIONS if d.key == "audio_queue_ok")
    )
    assert poll_ent.is_on is True
    assert audio_ent.is_on is False


@pytest.mark.asyncio
async def test_sensor_values_from_coordinator(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    for desc in SENSOR_DESCRIPTIONS:
        ent = RedDiscordDiagnosticSensor(coord, entry, desc)
        assert ent.native_value == desc.value_fn(coord)


@pytest.mark.asyncio
async def test_sensor_queue_length_and_voice_none_when_poll_fails(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def fail(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        if method == "HAREDRPC__QUEUE":
            raise RedRpcError("x")
        raise AssertionError(method)

    mock_rpc_call.side_effect = fail
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    ql = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "queue_length")
    )
    vc = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "voice_channel_id")
    )
    assert ql.native_value is None
    assert vc.native_value is None


@pytest.mark.asyncio
async def test_sensor_queue_length_none_when_queue_not_ok(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def not_ok(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {"ok": False, "error": "x"}
        raise AssertionError(method)

    mock_rpc_call.side_effect = not_ok
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    ql = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "queue_length")
    )
    vc = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "voice_channel_id")
    )
    assert ql.native_value is None
    assert vc.native_value is None


@pytest.mark.asyncio
async def test_sensor_queue_status_when_rpc_fails(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def fail(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        if method == "HAREDRPC__QUEUE":
            raise RedRpcError("x")
        raise AssertionError(method)

    mock_rpc_call.side_effect = fail
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    st = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "queue_status")
    )
    assert st.native_value == "rpc_unavailable"


@pytest.mark.asyncio
async def test_sensor_guild_id_always_from_config(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def fail(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        if method == "HAREDRPC__QUEUE":
            raise RedRpcError("x")
        raise AssertionError(method)

    mock_rpc_call.side_effect = fail
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    g = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "guild_id")
    )
    assert g.native_value == "1"


@pytest.mark.asyncio
async def test_in_voice_false_when_no_voice_channel(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def no_voice(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": None,
                "queue": [],
                "voice_channel_id": None,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = no_voice
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    voice_bin = RedDiscordDiagnosticBinary(
        coord, entry, next(d for d in BINARY_DESCRIPTIONS if d.key == "in_voice")
    )
    assert voice_bin.is_on is False


@pytest.mark.asyncio
async def test_sensor_queue_length_none_when_queue_not_list(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def bad_queue(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "paused": False, "now_playing": None, "queue": "nope"}
        raise AssertionError(method)

    mock_rpc_call.side_effect = bad_queue
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    ql = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "queue_length")
    )
    assert ql.native_value is None


@pytest.mark.asyncio
async def test_sensor_queue_status_invalid_and_unknown(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    coord.last_update_success = True
    coord.data = "not-a-dict"  # type: ignore[assignment]
    st = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "queue_status")
    )
    assert st.native_value == "invalid_response"

    coord.data = {"ok": False}
    assert st.native_value == "unknown_error"


@pytest.mark.asyncio
async def test_sensor_voice_channel_none_when_not_in_voice(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    async def no_voice(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": None,
                "queue": [],
                "voice_channel_id": None,
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = no_voice
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    vc = RedDiscordDiagnosticSensor(
        coord, entry, next(d for d in SENSOR_DESCRIPTIONS if d.key == "voice_channel_id")
    )
    assert vc.native_value is None


@pytest.mark.asyncio
async def test_binary_in_voice_non_dict_data_branch(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    coord.last_update_success = True
    coord.data = []  # type: ignore[assignment]
    voice_bin = RedDiscordDiagnosticBinary(
        coord, entry, next(d for d in BINARY_DESCRIPTIONS if d.key == "in_voice")
    )
    assert voice_bin.is_on is False


@pytest.mark.asyncio
async def test_sensor_entity_registered(
    hass: HomeAssistant,
    mock_rpc_call: object,
    entity_registry: er.EntityRegistry,
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eid = entity_registry.async_get_entity_id(
        SENSOR_DOMAIN, RPC_DOMAIN, f"{entry.entry_id}_diagnostic_queue_length"
    )
    assert eid is not None
    up_next_eid = entity_registry.async_get_entity_id(
        SENSOR_DOMAIN, RPC_DOMAIN, f"{entry.entry_id}_diagnostic_queue_items"
    )
    assert up_next_eid is not None
    up_next_reg = entity_registry.async_get(up_next_eid)
    assert up_next_reg is not None
    assert up_next_reg.disabled_by is None


@pytest.mark.asyncio
async def test_playlist_inventory_sensor_values_and_attrs(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    queue_coord = RedRpcQueueCoordinator(hass, entry)
    await queue_coord.async_refresh()

    playlist_coord = RedRpcPlaylistCoordinator(hass, entry)
    playlist_coord.last_update_success = True
    playlist_coord.data = {
        "ok": True,
        "playlists": [{"name": "Summer", "scope": "guild", "id": "summer"}],
        "error": "warn",
    }
    ent = RedDiscordPlaylistInventorySensor(playlist_coord, queue_coord, entry)
    assert ent.native_value == 1
    attrs = ent.extra_state_attributes
    assert isinstance(attrs.get("playlists"), list)
    assert attrs.get("error") == "warn"
    assert ent.device_info is not None

    playlist_coord.last_update_success = False
    assert ent.native_value is None

    playlist_coord.last_update_success = True
    playlist_coord.data = "bad"  # type: ignore[assignment]
    assert ent.native_value is None
    assert ent.extra_state_attributes == {}

    playlist_coord.data = {"ok": True, "playlists": "bad"}  # type: ignore[assignment]
    assert ent.native_value is None


@pytest.mark.asyncio
async def test_queue_inventory_sensor_values_and_attrs(
    hass: HomeAssistant, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(domain=RPC_DOMAIN, title="T", data=_entry_data())
    entry.add_to_hass(hass)
    queue_coord = RedRpcQueueCoordinator(hass, entry)
    await queue_coord.async_refresh()

    ent = RedDiscordQueueInventorySensor(queue_coord, entry)
    assert ent.native_value == "Q1"
    attrs = ent.extra_state_attributes
    assert isinstance(attrs.get("queue"), list)
    assert attrs["queue_count"] == 1
    assert attrs["queue"][0] == "Q1"
    assert isinstance(attrs.get("now_playing"), dict)
    assert ent.device_info is not None

    queue_coord.last_update_success = False
    assert ent.native_value is None

    queue_coord.last_update_success = True
    queue_coord.data = "bad"  # type: ignore[assignment]
    assert ent.native_value is None
    assert ent.extra_state_attributes == {}

    queue_coord.data = {"ok": True, "queue": "bad"}  # type: ignore[assignment]
    assert ent.native_value is None
