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


async def test_upstream_unavailable_raises_update_failed(hass: HomeAssistant) -> None:
    """UpstreamUnavailableError is re-raised as UpdateFailed (transient failure)."""
    mock_service = AsyncMock()
    mock_service.get_collection_schedule.side_effect = UpstreamUnavailableError("timeout")

    coordinator = LewishamUpdateCoordinator(hass, mock_service, MOCK_UPRN, MOCK_ADDRESS)
    with pytest.raises(UpdateFailed, match="unavailable"):
        await coordinator._async_update_data()


async def test_schedule_not_found_raises_update_failed(hass: HomeAssistant) -> None:
    """CollectionScheduleNotFoundError is re-raised as UpdateFailed."""
    mock_service = AsyncMock()
    mock_service.get_collection_schedule.side_effect = CollectionScheduleNotFoundError(
        "no schedule for uprn"
    )

    coordinator = LewishamUpdateCoordinator(hass, mock_service, MOCK_UPRN, MOCK_ADDRESS)
    with pytest.raises(UpdateFailed, match="No collection schedule"):
        await coordinator._async_update_data()


async def test_unexpected_domain_error_raises_update_failed(hass: HomeAssistant) -> None:
    """Other client domain errors are re-raised as UpdateFailed."""
    mock_service = AsyncMock()
    mock_service.get_collection_schedule.side_effect = DomainError("unexpected response")

    coordinator = LewishamUpdateCoordinator(hass, mock_service, MOCK_UPRN, MOCK_ADDRESS)
    with pytest.raises(UpdateFailed, match="Unexpected error"):
        await coordinator._async_update_data()
