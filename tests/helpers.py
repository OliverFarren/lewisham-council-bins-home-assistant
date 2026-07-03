"""Test helpers shared across supported Home Assistant versions."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


async def get_diagnostics_for_config_entry(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry: ConfigEntry[Any],
) -> dict[str, Any]:
    """Return diagnostics for a config entry through HA's HTTP endpoint."""
    assert await async_setup_component(hass, "diagnostics", {})
    await hass.async_block_till_done()

    client = await hass_client()
    response = await client.get(f"/api/diagnostics/config_entry/{config_entry.entry_id}")
    assert response.status == HTTPStatus.OK
    data = await response.json()
    return cast(dict[str, Any], data["data"])


async def get_diagnostics_for_device(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry: ConfigEntry[Any],
    device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a device through HA's HTTP endpoint."""
    assert await async_setup_component(hass, "diagnostics", {})

    client = await hass_client()
    response = await client.get(
        f"/api/diagnostics/config_entry/{config_entry.entry_id}/device/{device.id}"
    )
    assert response.status == HTTPStatus.OK
    data = await response.json()
    return cast(dict[str, Any], data["data"])
