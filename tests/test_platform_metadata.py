"""Platform metadata expectations."""

from __future__ import annotations

from custom_components.redbot_media_player.binary_sensor import PARALLEL_UPDATES as BINARY_PARALLEL
from custom_components.redbot_media_player.button import PARALLEL_UPDATES as BUTTON_PARALLEL
from custom_components.redbot_media_player.sensor import PARALLEL_UPDATES as SENSOR_PARALLEL


def test_parallel_updates_declared_for_all_platforms() -> None:
    """All entity platforms explicitly cap update concurrency."""
    assert BINARY_PARALLEL == 1
    assert SENSOR_PARALLEL == 1
    assert BUTTON_PARALLEL == 1
