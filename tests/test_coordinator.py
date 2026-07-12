"""Tests for the Lewisham Council DataUpdateCoordinator."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from lewisham_client import CollectionScheduleNotFoundError, DomainError, UpstreamUnavailableError

from custom_components.lewisham_council_bins.coordinator import LewishamUpdateCoordinator

from .conftest import MOCK_SCHEDULE, MOCK_UPRN, build_mock_entry

_SUPPORTS_CONFIG_ENTRY_KWARG = (
    "config_entry" in inspect.signature(TimestampDataUpdateCoordinator.__init__).parameters
)


async def test_successful_refresh_stores_schedule(hass: HomeAssistant) -> None:
    """A successful fetch stores the parsed schedule on the coordinator."""
    mock_service = AsyncMock()
    mock_service.get_collection_schedule.return_value = MOCK_SCHEDULE
    entry = build_mock_entry()

    coordinator = LewishamUpdateCoordinator(hass, entry, mock_service)
    await coordinator.async_refresh()

    assert coordinator.data is MOCK_SCHEDULE
    mock_service.get_collection_schedule.assert_awaited_once_with(MOCK_UPRN)


@pytest.mark.skipif(
    not _SUPPORTS_CONFIG_ENTRY_KWARG,
    reason="config_entry kwarg requires HA 2024.8+",
)
async def test_coordinator_is_linked_to_its_config_entry(hass: HomeAssistant) -> None:
    """On HA versions that support it, the coordinator is wired to its config entry.

    This is what lets HA attribute coordinator-originated logs/repairs to the
    right entry, and is required going into HA 2026.8 when the implicit
    config-entry-context fallback is removed.
    """
    mock_service = AsyncMock()
    entry = build_mock_entry()

    coordinator = LewishamUpdateCoordinator(hass, entry, mock_service)

    assert coordinator.config_entry is entry


@pytest.mark.parametrize(
    ("side_effect", "expected_key", "expected_placeholders", "expected_message"),
    [
        pytest.param(
            UpstreamUnavailableError("timeout"),
            "schedule_unavailable",
            {"error": "timeout"},
            "Lewisham Council service unavailable: timeout",
            id="upstream_unavailable",
        ),
        pytest.param(
            CollectionScheduleNotFoundError("no schedule for uprn"),
            "schedule_not_found",
            {"uprn": MOCK_UPRN, "error": "no schedule for uprn"},
            f"No collection schedule found for UPRN {MOCK_UPRN}: no schedule for uprn",
            id="schedule_not_found",
        ),
        pytest.param(
            DomainError("unexpected response"),
            "schedule_unexpected_error",
            {"error": "unexpected response"},
            "Unexpected error fetching collection schedule: unexpected response",
            id="unexpected_domain_error",
        ),
    ],
)
async def test_client_errors_raise_translated_update_failed(
    hass: HomeAssistant,
    side_effect: Exception,
    expected_key: str,
    expected_placeholders: dict[str, str],
    expected_message: str,
) -> None:
    """Client errors use translated UpdateFailed metadata or the pre-2024.12 fallback."""
    mock_service = AsyncMock()
    mock_service.get_collection_schedule.side_effect = side_effect
    entry = build_mock_entry()

    coordinator = LewishamUpdateCoordinator(hass, entry, mock_service)
    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()

    if hasattr(exc_info.value, "translation_key"):
        assert exc_info.value.translation_key == expected_key
        assert exc_info.value.translation_placeholders == expected_placeholders
    else:
        assert str(exc_info.value) == expected_message
