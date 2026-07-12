"""Lewisham Council Home Assistant integration.

Retrieves waste collection schedules from Lewisham Council via the
lewisham-council-client package. One config entry corresponds to one
residential address (identified by UPRN). A DataUpdateCoordinator polls
every 12 hours; the client's own schedule cache is disabled so the
coordinator is the authoritative refresh clock.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.util import dt as dt_util
from lewisham_client import CollectionSchedule, LewishamClient, LewishamParser, LewishamService

from .const import CONF_UPRN, DOMAIN
from .coordinator import LewishamCouncilBinsConfigEntry, LewishamUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: LewishamCouncilBinsConfigEntry) -> bool:
    """Set up Lewisham Council from a config entry.

    Injects HA's managed httpx session into the client so the integration
    shares the platform's connection pool and SSL context. The client will
    not close an injected session, so HA retains ownership of the lifecycle.
    """
    client = LewishamClient(http_client=get_async_client(hass))
    # include_raw_upstream lets a parser contract-drift failure attach a
    # truncated payload preview to its diagnostics attribute (see
    # diagnostics.py), which is scrubbed of the UPRN/address before it ever
    # reaches a downloadable diagnostics file. Logging is unaffected: the
    # preview is only ever logged when the parser's own logger is at DEBUG.
    service = LewishamService(
        client=client,
        parser=LewishamParser(include_raw_upstream=True),
        schedule_cache_ttl=timedelta(0),
        negative_cache_ttl=timedelta(0),
    )

    coordinator = LewishamUpdateCoordinator(hass, entry, service)

    # config_flow.py's async_step_select already fetched this UPRN's schedule
    # to validate it before creating the entry (test-before-configure). If
    # we're being set up right after that (same HA run), reuse its result
    # instead of hitting the same upstream scrape a second time. This is only
    # ever present for the entry's very first setup: it's popped below, and
    # is absent (and safely skipped) on every subsequent reload/restart.
    seeded_schedule = hass.data.get(DOMAIN, {}).pop(entry.data[CONF_UPRN], None)
    if isinstance(seeded_schedule, CollectionSchedule):
        coordinator.async_set_updated_data(seeded_schedule)
        # async_set_updated_data doesn't set last_update_success_time (only
        # the coordinator's own refresh machinery does), but diagnostics.py
        # reports it as the freshness signal, so set it explicitly here.
        coordinator.last_update_success_time = dt_util.utcnow()
    else:
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LewishamCouncilBinsConfigEntry) -> bool:
    """Unload a Lewisham Council config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
