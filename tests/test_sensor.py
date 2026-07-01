"""Tests for the Lewisham Council sensor platform."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.lewisham_council_bins.const import CONF_ADDRESS, CONF_UPRN, DOMAIN
from custom_components.lewisham_council_bins.coordinator import LewishamUpdateCoordinator
from custom_components.lewisham_council_bins.sensor import LewishamCollectionSensor

from .conftest import MOCK_ADDRESS, MOCK_SCHEDULE, MOCK_UPRN


@pytest.fixture
async def loaded_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a Lewisham Council config entry backed by MOCK_SCHEDULE."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_UPRN: MOCK_UPRN, CONF_ADDRESS: MOCK_ADDRESS},
        unique_id=MOCK_UPRN,
    )
    entry.add_to_hass(hass)

    mock_service = AsyncMock()
    mock_service.get_collection_schedule.return_value = MOCK_SCHEDULE

    with (
        patch(
            "custom_components.lewisham_council_bins.get_async_client",
            return_value=MagicMock(),
        ),
        patch("custom_components.lewisham_council_bins.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.LewishamService",
            return_value=mock_service,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


def _entity_id(hass: HomeAssistant, slug: str) -> str | None:
    """Look up the entity id for a sensor unique_id slug."""
    ent_reg = er.async_get(hass)
    return ent_reg.async_get_entity_id("sensor", DOMAIN, f"{MOCK_UPRN}_{slug}")


async def test_one_sensor_per_waste_stream(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """One sensor entity is created per CollectionEntry in the schedule."""
    for slug in ("food_waste", "recycling", "refuse"):
        assert _entity_id(hass, slug) is not None, f"Missing sensor for slug '{slug}'"


async def test_food_waste_native_value_is_next_collection(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """The Food Waste sensor state is the ISO-formatted next collection date."""
    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state is not None
    assert state.state == "2026-07-07"


async def test_refuse_with_no_date_is_unknown(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """A stream with next_collection=None reports an unknown state."""
    state = hass.states.get(_entity_id(hass, "refuse"))
    assert state is not None
    assert state.state == "unknown"


async def test_sensor_attributes_are_populated(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Sensor attributes include frequency, day, basis, source_url, and fetched_at."""
    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state is not None
    attrs = state.attributes
    assert attrs["frequency"] == "WEEKLY"
    assert attrs["day"] == "Monday"
    assert attrs["next_collection_basis"] == "published"
    assert "source_url" in attrs
    assert "fetched_at" in attrs


async def test_sensor_device_class_is_date(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Sensors are registered with the DATE device class."""
    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state is not None
    assert state.attributes.get("device_class") == SensorDeviceClass.DATE


async def test_entity_id_uses_lewisham_council_bins_prefix(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Entity IDs use the lewisham_council_bins_ prefix, not the address."""
    assert _entity_id(hass, "food_waste") == "sensor.lewisham_council_bins_food_waste"
    assert _entity_id(hass, "recycling") == "sensor.lewisham_council_bins_recycling"
    assert _entity_id(hass, "refuse") == "sensor.lewisham_council_bins_refuse"


async def test_unique_id_is_uprn_and_waste_type(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Unique IDs remain scoped to UPRN + waste stream for stable identification."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(_entity_id(hass, "food_waste"))
    assert entry is not None
    assert entry.unique_id == f"{MOCK_UPRN}_food_waste"


async def _refresh_with_frozen_time(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, frozen: datetime
) -> None:
    with patch("homeassistant.util.dt.now", return_value=frozen):
        await loaded_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()


async def test_days_until_collection_n_days(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """days_until_collection and collection_in reflect days when N > 1."""
    # MOCK_SCHEDULE food_waste next_collection = 2026-07-07; 4 days from 2026-07-03
    frozen = datetime(2026, 7, 3, 12, 0, tzinfo=dt_util.UTC)
    await _refresh_with_frozen_time(hass, loaded_entry, frozen)
    attrs = hass.states.get(_entity_id(hass, "food_waste")).attributes
    assert attrs["days_until_collection"] == 4
    assert attrs["collection_in"] == "4 days"


async def test_days_until_collection_tomorrow(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """collection_in is 'tomorrow' when the collection is 1 day away."""
    frozen = datetime(2026, 7, 6, 12, 0, tzinfo=dt_util.UTC)
    await _refresh_with_frozen_time(hass, loaded_entry, frozen)
    attrs = hass.states.get(_entity_id(hass, "food_waste")).attributes
    assert attrs["days_until_collection"] == 1
    assert attrs["collection_in"] == "tomorrow"


async def test_days_until_collection_today(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """collection_in is 'today' on the day of collection."""
    frozen = datetime(2026, 7, 7, 12, 0, tzinfo=dt_util.UTC)
    await _refresh_with_frozen_time(hass, loaded_entry, frozen)
    attrs = hass.states.get(_entity_id(hass, "food_waste")).attributes
    assert attrs["days_until_collection"] == 0
    assert attrs["collection_in"] == "today"


async def test_days_until_collection_none_when_no_date(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """days_until_collection and collection_in are None when no date is published."""
    # Refuse has next_collection=None in MOCK_SCHEDULE
    attrs = hass.states.get(_entity_id(hass, "refuse")).attributes
    assert attrs["days_until_collection"] is None
    assert attrs["collection_in"] is None


async def test_relative_timing_refreshes_at_midnight_without_polling(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Relative attributes should roll over at midnight without an HTTP refresh."""
    coordinator = loaded_entry.runtime_data
    get_schedule = coordinator.service.get_collection_schedule
    coordinator.update_interval = None
    coordinator._async_unsub_refresh()
    calls_before_midnight = get_schedule.await_count

    before_midnight = datetime(2026, 7, 6, 12, 0, tzinfo=dt_util.UTC)
    with patch("homeassistant.util.dt.now", return_value=before_midnight):
        coordinator.async_update_listeners()
        await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state.attributes["collection_in"] == "tomorrow"

    midnight = datetime(2026, 7, 7, 0, 0, tzinfo=dt_util.UTC)
    with patch("homeassistant.util.dt.now", return_value=midnight):
        async_fire_time_changed(hass, midnight)
        await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state.attributes["days_until_collection"] == 0
    assert state.attributes["collection_in"] == "today"
    assert get_schedule.await_count == calls_before_midnight


def test_sensor_without_coordinator_data_is_unavailable(hass: HomeAssistant) -> None:
    """A sensor is unavailable and has no value or attributes before data exists."""
    coordinator = LewishamUpdateCoordinator(
        hass,
        AsyncMock(),
        MOCK_UPRN,
        MOCK_ADDRESS,
    )
    sensor = LewishamCollectionSensor(coordinator, MOCK_SCHEDULE.collections[0])

    assert sensor.native_value is None
    assert sensor.available is False
    assert sensor.extra_state_attributes == {}
