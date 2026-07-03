"""Tests for the Lewisham Council DataUpdateCoordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from lewisham_client import CollectionScheduleNotFoundError, DomainError, UpstreamUnavailableError

from custom_components.lewisham_council_bins.coordinator import LewishamUpdateCoordinator

from .conftest import MOCK_ADDRESS, MOCK_SCHEDULE, MOCK_UPRN


async def test_successful_refresh_stores_schedule(hass: HomeAssistant) -> None:
    """A successful fetch stores the parsed schedule on the coordinator."""
    mock_service = AsyncMock()
    mock_service.get_collection_schedule.return_value = MOCK_SCHEDULE

    coordinator = LewishamUpdateCoordinator(hass, mock_service, MOCK_UPRN, MOCK_ADDRESS)
    await coordinator.async_refresh()

    assert coordinator.data is MOCK_SCHEDULE
    mock_service.get_collection_schedule.assert_awaited_once_with(MOCK_UPRN)


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

    coordinator = LewishamUpdateCoordinator(hass, mock_service, MOCK_UPRN, MOCK_ADDRESS)
    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()

    if hasattr(exc_info.value, "translation_key"):
        assert exc_info.value.translation_key == expected_key
        assert exc_info.value.translation_placeholders == expected_placeholders
    else:
        assert str(exc_info.value) == expected_message
