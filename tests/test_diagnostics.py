"""Tests for diagnostics endpoint."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.redbot_media_player.const import DOMAIN
from custom_components.redbot_media_player.diagnostics import (
    async_get_config_entry_diagnostics,
)


@pytest.mark.asyncio
async def test_config_entry_diagnostics_redacts_sensitive_fields(
    hass: object, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Red RPC",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
        options={"audiodb_api_key": "secret"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert payload["entry"]["data"]["host"] == "**REDACTED**"
    assert payload["entry"]["options"]["audiodb_api_key"] == "**REDACTED**"
