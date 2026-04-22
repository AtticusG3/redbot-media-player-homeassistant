"""Config flow for RedBot Media Player."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ACTOR_USER_ID,
    CONF_AUDIODB_API_KEY,
    CONF_AUDIODB_ENABLE,
    CONF_CHANNEL_ID,
    CONF_GUILD_ID,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DOMAIN,
)
from .audiodb import DEFAULT_AUDIODB_API_KEY
from .rpc import RedRpcError, verify_red_rpc

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_GUILD_ID): cv.string,
        vol.Required(CONF_CHANNEL_ID): cv.string,
        vol.Required(CONF_ACTOR_USER_ID): cv.string,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate we can reach Red RPC and the cog."""
    await verify_red_rpc(
        data[CONF_HOST],
        int(data[CONF_PORT]),
        int(data[CONF_GUILD_ID]),
    )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_AUDIODB_ENABLE, default=True): bool,
        vol.Optional(CONF_AUDIODB_API_KEY, default=DEFAULT_AUDIODB_API_KEY): str,
    }
)


class RedDiscordRpcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RedBot Media Player."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Options for TheAudioDB artwork lookup."""
        return RedDiscordRpcOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except RedRpcError as err:
                _LOGGER.error("RPC validation failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                uid = f"{user_input[CONF_HOST]}_{user_input[CONF_GUILD_ID]}"
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
                title = f"Red RPC ({user_input[CONF_HOST]})"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class RedDiscordRpcOptionsFlow(config_entries.OptionsFlow):
    """Integrations options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Album art via TheAudioDB."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,
                {
                    CONF_AUDIODB_ENABLE: opts.get(CONF_AUDIODB_ENABLE, True),
                    CONF_AUDIODB_API_KEY: opts.get(
                        CONF_AUDIODB_API_KEY, DEFAULT_AUDIODB_API_KEY
                    ),
                },
            ),
        )
