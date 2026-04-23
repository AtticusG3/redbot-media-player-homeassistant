"""Tests for queue coordinator."""

from __future__ import annotations

import types

import pytest
from pytest import MonkeyPatch
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.redbot_media_player.const import (
    CONF_AUDIODB_ENABLE,
    DOMAIN,
    FULL_HA_RED_RPC_METHODS,
)
from custom_components.redbot_media_player.coordinator import RedRpcQueueCoordinator
from custom_components.redbot_media_player.playlist_coordinator import RedRpcPlaylistCoordinator
from custom_components.redbot_media_player.rpc import RedRpcError


@pytest.mark.asyncio
async def test_effective_rpc_methods_default_full_set(
    hass: object, mock_rpc_call: object
) -> None:
    """When GET_METHODS was not stored, use FULL_HA_RED_RPC_METHODS."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    assert coord.rpc_method_names is None
    assert coord.effective_rpc_methods == FULL_HA_RED_RPC_METHODS


@pytest.mark.asyncio
async def test_fingerprint_empty_author_and_title(
    hass: object, mock_rpc_call: object
) -> None:
    """No fingerprint when both title and author are empty after normalization."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    assert (
        coord._fingerprint_now_playing(  # noqa: SLF001
            {"now_playing": {"title": "", "author": "", "uri": "u"}},
        )
        is None
    )


@pytest.mark.asyncio
async def test_sync_audiodb_skips_when_now_playing_not_dict(
    hass: object, mock_rpc_call: object, monkeypatch: MonkeyPatch
) -> None:
    """Defensive: do not fetch art if payload is inconsistent."""
    calls: list[object] = []

    async def track(*a: object, **k: object) -> None:
        calls.append(True)

    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.async_fetch_album_art_url",
        track,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)

    coord._fingerprint_now_playing = types.MethodType(  # type: ignore[assignment]
        lambda self, data: "forced-fp", coord
    )

    await coord._async_sync_audiodb_art({"now_playing": "not-a-dict"})
    assert calls == []


@pytest.mark.asyncio
async def test_coordinator_refresh_success(
    hass: object, mock_rpc_call: object
) -> None:
    """Coordinator stores queue payload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    assert coord.last_update_success
    assert coord.data is not None
    assert coord.data["ok"] is True


@pytest.mark.asyncio
async def test_coordinator_refresh_rpc_error(
    hass: object, mock_rpc_call: object
) -> None:
    """RedRpcError becomes failed update."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    mock_rpc_call.side_effect = RedRpcError("down")
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    assert not coord.last_update_success


@pytest.mark.asyncio
async def test_effective_rpc_methods_when_probed(
    hass: object, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    coord.rpc_method_names = frozenset({"HAREDRPC__QUEUE"})
    assert coord.effective_rpc_methods == frozenset({"HAREDRPC__QUEUE"})


@pytest.mark.asyncio
async def test_coordinator_audiodb_disabled_skips_fetch(
    hass: object, mock_rpc_call: object, monkeypatch: MonkeyPatch
) -> None:
    calls: list[object] = []

    async def track(*a: object, **k: object) -> None:
        calls.append(True)

    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.async_fetch_album_art_url",
        track,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
        options={CONF_AUDIODB_ENABLE: False},
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    assert calls == []


@pytest.mark.asyncio
async def test_coordinator_audiodb_exception_clears_art(
    hass: object, mock_rpc_call: object, monkeypatch: MonkeyPatch
) -> None:
    async def boom(*a: object, **k: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.async_fetch_album_art_url",
        boom,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    assert coord.media_image_url is None


@pytest.mark.asyncio
async def test_coordinator_idle_no_audiodb_when_fp_none(
    hass: object, mock_rpc_call: object, monkeypatch: MonkeyPatch
) -> None:
    """When nothing is playing, fingerprint is None and fetch is skipped."""
    calls: list[object] = []

    async def track(*a: object, **k: object) -> None:
        calls.append(True)

    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.async_fetch_album_art_url",
        track,
    )

    async def idle(
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
            }
        raise AssertionError(method)

    mock_rpc_call.side_effect = idle
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    assert calls == []


@pytest.mark.asyncio
async def test_coordinator_fp_none_after_track_clears_art(
    hass: object, mock_rpc_call: object, monkeypatch: MonkeyPatch
) -> None:
    """Going from playing to idle hits fp-is-None path after a non-None fingerprint."""
    phase = 0

    async def track(*a: object, **k: object) -> None:
        return None

    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.async_fetch_album_art_url",
        track,
    )

    async def queue(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict:
        nonlocal phase
        if method != "HAREDRPC__QUEUE":
            raise AssertionError(method)
        phase += 1
        if phase == 1:
            return {
                "ok": True,
                "paused": False,
                "now_playing": {
                    "title": "T",
                    "author": "A",
                    "uri": "u",
                },
                "queue": [],
            }
        return {
            "ok": True,
            "paused": False,
            "now_playing": None,
            "queue": [],
        }

    mock_rpc_call.side_effect = queue
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    assert coord._track_art_fingerprint is not None  # noqa: SLF001
    await coord.async_refresh()
    assert coord._track_art_fingerprint is None  # noqa: SLF001
    assert coord.media_image_url is None


@pytest.mark.asyncio
async def test_coordinator_invalid_payload(
    hass: object, mock_rpc_call: object
) -> None:
    """Non-dict queue response fails update."""

    async def bad(*a: object, **k: object) -> str:
        return "not-a-dict"

    mock_rpc_call.side_effect = bad
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)
    await coord.async_refresh()
    assert not coord.last_update_success


@pytest.mark.asyncio
async def test_playlist_coordinator_success_and_invalid_payload(
    hass: object, mock_rpc_call: object
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcPlaylistCoordinator(hass, entry)

    async def ok(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict[str, object]:
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True}
        raise AssertionError(method)

    mock_rpc_call.side_effect = ok
    await coord.async_refresh()
    assert coord.last_update_success
    assert coord.data["playlists"] == []

    async def non_dict(*a: object, **k: object) -> str:
        return "bad"

    mock_rpc_call.side_effect = non_dict
    await coord.async_refresh()
    assert not coord.last_update_success

    async def bad_list(*a: object, **k: object) -> dict[str, object]:
        return {"ok": True, "playlists": "bad"}

    mock_rpc_call.side_effect = bad_list
    await coord.async_refresh()
    assert not coord.last_update_success


@pytest.mark.asyncio
async def test_queue_coordinator_creates_and_clears_repairs_issue(
    hass: object, mock_rpc_call: object, monkeypatch: MonkeyPatch
) -> None:
    created: list[tuple[str, str]] = []
    deleted: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.ir.async_create_issue",
        lambda hass_obj, domain, issue_id, **kwargs: created.append((domain, issue_id)),
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.ir.async_delete_issue",
        lambda hass_obj, domain, issue_id: deleted.append((domain, issue_id)),
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcQueueCoordinator(hass, entry)

    mock_rpc_call.side_effect = RedRpcError("down")
    await coord.async_refresh()
    assert created
    assert created[-1][0] == DOMAIN

    async def ok(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict[str, object]:
        if method == "HAREDRPC__QUEUE":
            return {"ok": True, "queue": []}
        raise AssertionError(method)

    mock_rpc_call.side_effect = ok
    await coord.async_refresh()
    assert deleted
    assert deleted[-1][0] == DOMAIN


@pytest.mark.asyncio
async def test_playlist_coordinator_creates_and_clears_repairs_issue(
    hass: object, mock_rpc_call: object, monkeypatch: MonkeyPatch
) -> None:
    created: list[tuple[str, str]] = []
    deleted: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "custom_components.redbot_media_player.playlist_coordinator.ir.async_create_issue",
        lambda hass_obj, domain, issue_id, **kwargs: created.append((domain, issue_id)),
    )
    monkeypatch.setattr(
        "custom_components.redbot_media_player.playlist_coordinator.ir.async_delete_issue",
        lambda hass_obj, domain, issue_id: deleted.append((domain, issue_id)),
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            "host": "127.0.0.1",
            "port": 6133,
            "guild_id": "1",
            "channel_id": "2",
            "actor_user_id": "3",
        },
    )
    entry.add_to_hass(hass)
    coord = RedRpcPlaylistCoordinator(hass, entry)

    mock_rpc_call.side_effect = RedRpcError("down")
    await coord.async_refresh()
    assert created
    assert created[-1][0] == DOMAIN

    async def ok(
        host: str,
        port: int,
        method: str,
        params: object | None = None,
        *,
        timeout: float = 120.0,
    ) -> dict[str, object]:
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {"ok": True, "playlists": []}
        raise AssertionError(method)

    mock_rpc_call.side_effect = ok
    await coord.async_refresh()
    assert deleted
    assert deleted[-1][0] == DOMAIN
