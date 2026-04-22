"""Pytest fixtures for redbot_media_player."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

# Repo root must be on sys.path so HA's loader finds custom_components/ (venv-friendly;
# avoids IntegrationNotFound when the package is not installed under site-packages).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_repo = str(_REPO_ROOT)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

import pytest
import pytest_socket

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_fixture_setup(fixturedef: pytest.FixtureDef, request: pytest.FixtureRequest) -> None:
    """HA pytest_runtest_setup disables sockets; Proactor event loop needs them on Windows."""
    if sys.platform == "win32" and fixturedef.argname == "event_loop":
        pytest_socket.enable_socket()
    yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components from the repo root."""
    yield


@pytest.fixture(autouse=True)
def patch_audiodb_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real HTTPS to TheAudioDB during coordinator refresh."""

    async def _no_art(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(
        "custom_components.redbot_media_player.coordinator.async_fetch_album_art_url",
        _no_art,
    )
    yield


@pytest.fixture
def mock_rpc_call(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub WebSocket RPC; override side_effect per test if needed."""

    async def _fake(
        host: str,
        port: int,
        method: str,
        params: list[Any] | None = None,
        *,
        timeout: float = 120.0,
    ) -> Any:
        if method == "GET_METHODS":
            return [
                "GET_METHODS",
                "HAREDRPC__QUEUE",
                "HAREDRPC__PLAYLIST_LIST",
                "HAREDRPC__PLAY",
                "HAREDRPC__BUMPPLAY",
                "HAREDRPC__PAUSE",
                "HAREDRPC__ENQUEUE",
                "HAREDRPC__PLAYLIST_START",
                "HAREDRPC__PLAYLIST_SAVE_START",
                "HAREDRPC__STOP",
                "HAREDRPC__SKIP",
                "HAREDRPC__PREVIOUS",
                "HAREDRPC__DISCONNECT",
                "HAREDRPC__SUMMON",
                "HAREDRPC__QUEUE_CLEAR",
                "HAREDRPC__SHUFFLE",
                "HAREDRPC__REPEAT",
                "HAREDRPC__SEEK",
                "HAREDRPC__VOLUME",
                "HAREDRPC__VOICE_STATE",
            ]
        if method == "HAREDRPC__QUEUE":
            return {
                "ok": True,
                "paused": False,
                "now_playing": {
                    "title": "Test Track",
                    "uri": "https://example.com/watch?v=1",
                    "author": "Artist",
                    "length": 120000,
                },
                "position_ms": 15000,
                "queue": [{"title": "Q1"}],
                "guild_name": "Test Guild",
                "voice_channel_name": "Riding Tunes",
                "voice_channel_id": 9001,
                "shuffle": False,
                "repeat": False,
                "volume_percent": 50,
                "bot_self_mute": False,
                "bot_self_deaf": False,
            }
        if method == "HAREDRPC__PLAYLIST_LIST":
            return {
                "ok": True,
                "playlists": [
                    {"name": "SummerHits", "scope": "guild", "id": "guild:summerhits"},
                    {"name": "MyMix", "scope": "guild", "id": "guild:mymix"},
                ],
            }
        if method in (
            "HAREDRPC__PLAY",
            "HAREDRPC__BUMPPLAY",
            "HAREDRPC__ENQUEUE",
            "HAREDRPC__PAUSE",
            "HAREDRPC__PLAYLIST_START",
            "HAREDRPC__PLAYLIST_SAVE_START",
            "HAREDRPC__STOP",
            "HAREDRPC__SKIP",
            "HAREDRPC__PREVIOUS",
            "HAREDRPC__DISCONNECT",
            "HAREDRPC__SUMMON",
            "HAREDRPC__QUEUE_CLEAR",
            "HAREDRPC__SHUFFLE",
            "HAREDRPC__REPEAT",
            "HAREDRPC__SEEK",
            "HAREDRPC__VOLUME",
            "HAREDRPC__VOICE_STATE",
        ):
            return {"ok": True}
        raise AssertionError(f"unexpected method {method}")

    mock = AsyncMock(side_effect=_fake)
    for mod in (
        "custom_components.redbot_media_player.rpc.rpc_call",
        "custom_components.redbot_media_player.coordinator.rpc_call",
        "custom_components.redbot_media_player.playlist_coordinator.rpc_call",
        "custom_components.redbot_media_player.rpc_call",
        "custom_components.redbot_media_player.media_player.rpc_call",
        "custom_components.redbot_media_player.button.rpc_call",
    ):
        monkeypatch.setattr(mod, mock)
    return mock
