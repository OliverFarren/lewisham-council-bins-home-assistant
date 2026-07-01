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
from lewisham_client import LewishamClient, LewishamParser, LewishamService

from .const import CONF_ADDRESS, CONF_UPRN
from .coordinator import LewishamCouncilBinsConfigEntry, LewishamUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: LewishamCouncilBinsConfigEntry) -> bool:
    """Set up Lewisham Council from a config entry.

    Injects HA's managed httpx session into the client so the integration
    shares the platform's connection pool and SSL context. The client will
    not close an injected session, so HA retains ownership of the lifecycle.
    """
    uprn: str = entry.data[CONF_UPRN]
    address: str = entry.data[CONF_ADDRESS]

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

    coordinator = LewishamUpdateCoordinator(hass, service, uprn, address)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LewishamCouncilBinsConfigEntry) -> bool:
    """Unload a Lewisham Council config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
