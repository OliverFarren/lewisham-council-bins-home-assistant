"""Sensor platform for Lewisham Council waste collection dates."""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from lewisham_client import CollectionEntry

from .const import DOMAIN, MANUFACTURER
from .coordinator import LewishamCouncilBinsConfigEntry, LewishamUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# All sensors share a coordinator and do not make individual update requests.
PARALLEL_UPDATES = 0


def _slug(waste_type: str) -> str:
    """Convert a waste-type string (e.g. 'Food Waste') to a stable lowercase slug."""
    return re.sub(r"[^a-z0-9]+", "_", waste_type.lower()).strip("_")


# Ordered keyword -> translation_key mapping; entries are checked in order and
# the first match wins, so more specific phrases (e.g. a "non-recyclable" waste
# stream, which councils use as a name for general refuse) must be listed before
# the broader keyword they would otherwise be mistaken for ("recycl"). Keys must
# have a matching entry in strings.json (entity name) and icons.json (entity
# icon). Any waste-type string that matches none of these keywords falls back to
# "other", so an unexpected new collection type from the council still gets a
# valid name and icon.
_TRANSLATION_KEY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("non-recycl", "refuse"),
    ("non recycl", "refuse"),
    ("food", "food_waste"),
    ("garden", "garden_waste"),
    ("recycl", "recycling"),
    ("refuse", "refuse"),
    ("rubbish", "refuse"),
)


def _translation_key(waste_type: str) -> str:
    """Classify a waste-type string into a known translation key, or 'other'."""
    lowered = waste_type.lower()
    for keyword, key in _TRANSLATION_KEY_KEYWORDS:
        if keyword in lowered:
            return key
    return "other"


def _identity_keys(collections: Sequence[CollectionEntry]) -> list[str]:
    """Assign each collection a key that survives a council rename where possible.

    Prefers the classified translation key (e.g. "food_waste") over a slug of
    the raw name, since a rename that keeps the same kind of waste (e.g.
    "Food Waste" -> "Food Waste (weekly)") still classifies the same way and
    so keeps the same entity identity. Falls back to a slug of the full name
    when a translation key would be ambiguous (two streams of the same kind,
    or two unclassified "other" streams), matching prior behaviour for that
    case.
    """
    keys = [_translation_key(c.waste_type) for c in collections]
    counts = Counter(keys)
    return [
        key if key != "other" and counts[key] == 1 else _slug(c.waste_type)
        for c, key in zip(collections, keys, strict=True)
    ]


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
    entry: LewishamCouncilBinsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lewisham Council sensors from a config entry.

    One sensor is created per waste stream returned by the first coordinator
    refresh. A rename that keeps the same kind of waste (see
    `_identity_keys`) is picked up automatically; re-loading the config entry
    is only needed if Lewisham adds a new stream or a rename changes what
    kind of waste a stream classifies as.
    """
    coordinator = entry.runtime_data
    collections = coordinator.data.collections
    async_add_entities(
        LewishamCollectionSensor(coordinator, collection, identity_key)
        for collection, identity_key in zip(collections, _identity_keys(collections), strict=True)
    )

    @callback
    def _handle_midnight(_now: datetime) -> None:
        """Refresh stale coordinator data or update relative attributes locally."""
        today = dt_util.now().date()
        if any(
            collection.next_collection is not None and collection.next_collection < today
            for collection in coordinator.data.collections
        ):
            entry.async_create_task(hass, coordinator.async_request_refresh())
            return
        coordinator.async_update_listeners()

    entry.async_on_unload(
        async_track_time_change(
            hass,
            _handle_midnight,
            hour=0,
            minute=0,
            second=0,
        )
    )


class LewishamCollectionSensor(CoordinatorEntity[LewishamUpdateCoordinator], SensorEntity):
    """A sensor reporting the next collection date for one waste stream.

    The sensor is unavailable if its stream disappears from the coordinator's
    data (e.g. Lewisham stops returning it). It shows an unknown state if no
    next collection date could be worked out for it at all. That's rare for
    the normal Food Waste / Recycling / Refuse schedule: see the README's
    "How the next collection date is determined" section for why, and
    next_collection_basis for how a given date was worked out.
    """

    _attr_device_class = SensorDeviceClass.DATE
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LewishamUpdateCoordinator,
        collection: CollectionEntry,
        identity_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._identity_key = identity_key
        self._waste_type = waste_type = collection.waste_type
        self._attr_unique_id = f"{coordinator.uprn}_{identity_key}"
        self._attr_translation_key = _translation_key(waste_type)
        self._attr_translation_placeholders = {"waste_type": waste_type}
        self.entity_id = f"sensor.lewisham_council_bins_{_slug(waste_type)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.uprn)},
            name=coordinator.address,
            manufacturer=MANUFACTURER,
            model="Lewisham Council Bin Collection Schedule",
            configuration_url=coordinator.data.source_url if coordinator.data else None,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _current_entry(self) -> CollectionEntry | None:
        """Return this sensor's entry from the latest coordinator data, or None.

        First tries an exact match on the waste-type name this sensor was
        created with. That covers the normal case (nothing renamed) without
        caring what other streams currently exist.

        If no exact match is found, the stream may have been renamed by the
        council. As a fallback, look for a single current stream that
        classifies into the same category (e.g. "food_waste") as this
        sensor's original name. If exactly one does, treat it as the same
        stream. If none do, or more than one does, we can't tell which
        stream (if any) this sensor now corresponds to, so it goes
        unavailable until the config entry is reloaded.
        """
        if self.coordinator.data is None:
            return None
        collections = self.coordinator.data.collections
        exact = next((e for e in collections if e.waste_type == self._waste_type), None)
        if exact is not None:
            return exact
        category = _translation_key(self._waste_type)
        if category == "other":
            return None
        candidates = [e for e in collections if _translation_key(e.waste_type) == category]
        return candidates[0] if len(candidates) == 1 else None

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
