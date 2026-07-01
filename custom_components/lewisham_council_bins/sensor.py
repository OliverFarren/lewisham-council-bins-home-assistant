"""Sensor platform for Lewisham Council waste collection dates."""

from __future__ import annotations

import logging
import re
from datetime import date

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from lewisham_client import CollectionEntry

from .const import DOMAIN, MANUFACTURER
from .coordinator import LewishamUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _slug(waste_type: str) -> str:
    """Convert a waste-type string (e.g. 'Food Waste') to a stable lowercase slug."""
    return re.sub(r"[^a-z0-9]+", "_", waste_type.lower()).strip("_")


def _days_until(next_collection: date | None) -> int | None:
    if next_collection is None:
        return None
    return (next_collection - dt_util.now().date()).days


def _collection_in(days: int | None) -> str | None:
    if days is None:
        return None
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"{days} days"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lewisham Council sensors from a config entry.

    One sensor is created per waste stream returned by the first coordinator
    refresh. If Lewisham adds or renames streams in future, re-loading the
    config entry will pick up the change.
    """
    coordinator: LewishamUpdateCoordinator = entry.runtime_data
    async_add_entities(
        LewishamCollectionSensor(coordinator, collection)
        for collection in coordinator.data.collections
    )


class LewishamCollectionSensor(CoordinatorEntity[LewishamUpdateCoordinator], SensorEntity):
    """A sensor reporting the next collection date for one waste stream.

    The sensor is unavailable if the stream disappears from the coordinator's
    data (e.g. Lewisham removes it) and returns an unknown state when the next
    date is not published (common for fortnightly streams mid-cycle).
    """

    _attr_device_class = SensorDeviceClass.DATE
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LewishamUpdateCoordinator,
        collection: CollectionEntry,
    ) -> None:
        super().__init__(coordinator)
        self._waste_type = collection.waste_type
        slug = _slug(collection.waste_type)
        self._attr_unique_id = f"{coordinator.uprn}_{slug}"
        self._attr_name = collection.waste_type
        self.entity_id = f"sensor.lewisham_council_bins_{slug}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.uprn)},
            name=coordinator.address,
            manufacturer=MANUFACTURER,
        )

    def _current_entry(self) -> CollectionEntry | None:
        """Return this sensor's entry from the latest coordinator data, or None."""
        if self.coordinator.data is None:
            return None
        return next(
            (e for e in self.coordinator.data.collections if e.waste_type == self._waste_type),
            None,
        )

    @property
    def native_value(self) -> date | None:
        """Return the next collection date, or None when not yet published."""
        entry = self._current_entry()
        return entry.next_collection if entry is not None else None

    @property
    def available(self) -> bool:
        """Return False when the coordinator is down or the stream has disappeared."""
        return super().available and self._current_entry() is not None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Return frequency, weekday, basis, provenance, and relative timing."""
        entry = self._current_entry()
        if entry is None:
            return {}
        days = _days_until(entry.next_collection)
        return {
            "frequency": entry.frequency,
            "day": entry.day,
            "next_collection_basis": entry.next_collection_basis,
            "source_url": self.coordinator.data.source_url,
            "fetched_at": self.coordinator.data.fetched_at.isoformat(),
            "days_until_collection": days,
            "collection_in": _collection_in(days),
        }
