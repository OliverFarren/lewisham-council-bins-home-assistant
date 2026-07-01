"""DataUpdateCoordinator for Lewisham Council waste collection schedules."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from lewisham_client import (
    AddressNotFoundError,
    CollectionSchedule,
    CollectionScheduleNotFoundError,
    DomainError,
    LewishamService,
    UpstreamUnavailableError,
)

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LewishamUpdateCoordinator(DataUpdateCoordinator[CollectionSchedule]):
    """Coordinator that fetches and caches the collection schedule for one address.

    One coordinator instance is created per config entry (i.e. per UPRN). HA's
    DataUpdateCoordinator owns the 12-hour refresh interval; the client's own
    schedule cache is disabled so the coordinator is the single source of truth
    for refresh timing.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        service: LewishamService,
        uprn: str,
        address: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{uprn}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.service = service
        self.uprn = uprn
        self.address = address

    async def _async_update_data(self) -> CollectionSchedule:
        """Fetch the current collection schedule from Lewisham Council."""
        try:
            return await self.service.get_collection_schedule(self.uprn)
        except UpstreamUnavailableError as err:
            raise UpdateFailed(f"Lewisham Council service unavailable: {err}") from err
        except (CollectionScheduleNotFoundError, AddressNotFoundError) as err:
            raise UpdateFailed(f"No collection schedule found for UPRN {self.uprn}: {err}") from err
        except DomainError as err:
            raise UpdateFailed(f"Unexpected error fetching collection schedule: {err}") from err
