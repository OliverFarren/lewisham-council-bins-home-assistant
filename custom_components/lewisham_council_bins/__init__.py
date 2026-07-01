"""Lewisham Council Home Assistant integration.

Retrieves waste collection schedules from Lewisham Council via the
lewisham-council-client package. One config entry corresponds to one
residential address (identified by UPRN). A DataUpdateCoordinator polls
every 12 hours; the client's own schedule cache is disabled so the
coordinator is the authoritative refresh clock.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from lewisham_client import LewishamClient, LewishamService

from .const import CONF_ADDRESS, CONF_UPRN
from .coordinator import LewishamUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lewisham Council from a config entry.

    Injects HA's managed httpx session into the client so the integration
    shares the platform's connection pool and SSL context. The client will
    not close an injected session, so HA retains ownership of the lifecycle.
    """
    uprn: str = entry.data[CONF_UPRN]
    address: str = entry.data[CONF_ADDRESS]

    client = LewishamClient(http_client=get_async_client(hass))
    service = LewishamService(
        client=client,
        schedule_cache_ttl=timedelta(0),
        negative_cache_ttl=timedelta(0),
    )

    coordinator = LewishamUpdateCoordinator(hass, service, uprn, address)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Lewisham Council config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
