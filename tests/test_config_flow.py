"""Tests for config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.redbot_media_player.const import (
    CONF_AUDIODB_API_KEY,
    CONF_AUDIODB_ENABLE,
    DOMAIN,
)


def _valid_user_input() -> dict[str, object]:
    return {
        "host": "127.0.0.1",
        "port": 6133,
        "guild_id": "1",
        "channel_id": "2",
        "actor_user_id": "3",
    }


@pytest.mark.asyncio
async def test_config_flow_user_shows_form(hass: object) -> None:
    """First step is user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_config_flow_create_entry(hass: object) -> None:
    """Successful validation creates an entry."""
    with patch(
        "custom_components.redbot_media_player.config_flow.verify_red_rpc",
        new_callable=AsyncMock,
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"],
            user_input=_valid_user_input(),
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert "Red RPC" in result["title"]


@pytest.mark.asyncio
async def test_config_flow_cannot_connect(hass: object) -> None:
    """RedRpcError surfaces as cannot_connect."""
    from custom_components.redbot_media_player.rpc import RedRpcError

    with patch(
        "custom_components.redbot_media_player.config_flow.verify_red_rpc",
        new_callable=AsyncMock,
        side_effect=RedRpcError("refused"),
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"],
            user_input=_valid_user_input(),
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_config_flow_unknown_error(hass: object) -> None:
    """Unexpected exceptions map to unknown."""
    with patch(
        "custom_components.redbot_media_player.config_flow.verify_red_rpc",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"],
            user_input=_valid_user_input(),
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "unknown"


@pytest.mark.asyncio
async def test_config_flow_duplicate_aborts(hass: object) -> None:
    """Same host+guild unique_id aborts second configure."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    with patch(
        "custom_components.redbot_media_player.config_flow.verify_red_rpc",
        new_callable=AsyncMock,
    ):
        existing = MockConfigEntry(
            domain=DOMAIN,
            unique_id="127.0.0.1_1",
            title="Existing",
            data=dict(_valid_user_input()),
        )
        existing.add_to_hass(hass)

        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"],
            user_input=_valid_user_input(),
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_options_flow_create_entry(
    hass: object, mock_rpc_call: object
) -> None:
    """TheAudioDB options can be saved."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Red RPC",
        data=dict(_valid_user_input()),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    opt = await hass.config_entries.options.async_init(entry.entry_id)
    assert opt["type"] == FlowResultType.FORM
    assert opt["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        opt["flow_id"],
        user_input={
            CONF_AUDIODB_ENABLE: False,
            CONF_AUDIODB_API_KEY: "2",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.options[CONF_AUDIODB_ENABLE] is False


@pytest.mark.asyncio
async def test_reauth_confirm_updates_entry(hass: object) -> None:
    """Reauth validates input and updates entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Red RPC",
        data=dict(_valid_user_input()),
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.redbot_media_player.config_flow.verify_red_rpc",
        new_callable=AsyncMock,
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"],
            user_input={
                **_valid_user_input(),
                "host": "localhost",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.data["host"] == "localhost"


@pytest.mark.asyncio
async def test_reconfigure_updates_entry(hass: object, mock_rpc_call: object) -> None:
    """Reconfigure validates input and updates config entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Red RPC",
        unique_id="127.0.0.1_1",
        data=dict(_valid_user_input()),
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.redbot_media_player.config_flow.verify_red_rpc",
        new_callable=AsyncMock,
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"],
            user_input={
                **_valid_user_input(),
                "host": "localhost",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.data["host"] == "localhost"
