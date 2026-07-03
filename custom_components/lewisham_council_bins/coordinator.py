"""DataUpdateCoordinator for Lewisham Council waste collection schedules."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
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

# Keep these English fallbacks in sync with strings.json. Home Assistant before
# 2024.12 cannot construct a translated UpdateFailed.
_UPDATE_FAILED_FALLBACKS = {
    "schedule_unavailable": "Lewisham Council service unavailable: {error}",
    "schedule_not_found": "No collection schedule found for UPRN {uprn}: {error}",
    "schedule_unexpected_error": "Unexpected error fetching collection schedule: {error}",
}


def _update_failed(translation_key: str, **placeholders: str) -> UpdateFailed:
    """Build a translated UpdateFailed, with a fallback for HA before 2024.12."""
    try:
        return UpdateFailed(
            translation_domain=DOMAIN,
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )
    except TypeError:
        # UpdateFailed was a plain Exception until HA 2024.12 and therefore
        # rejected the translation keyword arguments.
        return UpdateFailed(_UPDATE_FAILED_FALLBACKS[translation_key].format(**placeholders))


class LewishamUpdateCoordinator(TimestampDataUpdateCoordinator[CollectionSchedule]):
    """Coordinator that fetches and caches the collection schedule for one address.

    One coordinator instance is created per config entry (i.e. per UPRN). HA's
    DataUpdateCoordinator owns the 12-hour refresh interval; the client's own
    schedule cache is disabled so the coordinator is the single source of truth
    for refresh timing. TimestampDataUpdateCoordinator adds last_update_success_time,
    which diagnostics.py reports.
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
            raise _update_failed("schedule_unavailable", error=str(err)) from err
        except (CollectionScheduleNotFoundError, AddressNotFoundError) as err:
            raise _update_failed("schedule_not_found", uprn=self.uprn, error=str(err)) from err
        except DomainError as err:
            raise _update_failed("schedule_unexpected_error", error=str(err)) from err


type LewishamCouncilBinsConfigEntry = ConfigEntry[LewishamUpdateCoordinator]
