"""Tests for helpers."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.redbot_media_player.const import (
    CONF_ACTOR_USER_ID,
    CONF_AUDIODB_API_KEY,
    CONF_AUDIODB_ENABLE,
    CONF_CHANNEL_ID,
    CONF_GUILD_ID,
    CONF_HOST,
    CONF_PORT,
)
from custom_components.redbot_media_player.helpers import get_audiodb_config, get_rpc_params


def test_get_rpc_params() -> None:
    """get_rpc_params parses entry.data."""
    entry = SimpleNamespace(
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: "6133",
            CONF_GUILD_ID: "111",
            CONF_CHANNEL_ID: "222",
            CONF_ACTOR_USER_ID: "333",
        },
    )
    p = get_rpc_params(entry)  # type: ignore[arg-type]
    assert p == {
        "host": "127.0.0.1",
        "port": 6133,
        "guild_id": 111,
        "channel_id": 222,
        "actor_id": 333,
    }


def test_get_rpc_params_without_actor() -> None:
    """Blank actor in config maps to None for actor_id."""
    entry = SimpleNamespace(
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: "6133",
            CONF_GUILD_ID: "111",
            CONF_CHANNEL_ID: "222",
            CONF_ACTOR_USER_ID: "   ",
        },
    )
    p = get_rpc_params(entry)  # type: ignore[arg-type]
    assert p["actor_id"] is None


def test_get_audiodb_config_defaults() -> None:
    entry = SimpleNamespace(options={})
    en, key = get_audiodb_config(entry)  # type: ignore[arg-type]
    assert en is True
    assert key == "2"


def test_get_audiodb_config_explicit() -> None:
    entry = SimpleNamespace(
        options={
            CONF_AUDIODB_ENABLE: False,
            CONF_AUDIODB_API_KEY: "99",
        }
    )
    en, key = get_audiodb_config(entry)  # type: ignore[arg-type]
    assert en is False
    assert key == "99"


def test_get_audiodb_config_empty_key_uses_default() -> None:
    entry = SimpleNamespace(options={CONF_AUDIODB_API_KEY: "   "})
    _en, key = get_audiodb_config(entry)  # type: ignore[arg-type]
    assert key == "2"


def test_get_audiodb_config_non_string_key() -> None:
    entry = SimpleNamespace(options={CONF_AUDIODB_API_KEY: 42})
    _en, key = get_audiodb_config(entry)  # type: ignore[arg-type]
    assert key == "42"
