"""Tests for the Lewisham Council sensor platform."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.lewisham_council_bins.const import DOMAIN
from custom_components.lewisham_council_bins.coordinator import LewishamUpdateCoordinator
from custom_components.lewisham_council_bins.sensor import (
    LewishamCollectionSensor,
    _translation_key,
)

from .conftest import MOCK_ADDRESS, MOCK_SCHEDULE, MOCK_UPRN, build_mock_entry


@pytest.fixture
async def loaded_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a Lewisham Council config entry backed by MOCK_SCHEDULE."""
    entry = build_mock_entry()
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


def _next_local_midnight() -> datetime:
    """Return the next local midnight, strictly after the real current time.

    async_fire_time_changed only fires a scheduled timer if the injected
    time looks genuinely further into the future than the real wall clock
    (pytest_homeassistant_custom_component compares the jump against real
    time.time()). A hardcoded calendar date eventually falls in the past
    relative to whenever the suite actually runs and the timer silently
    never fires, so the rollover instant must always be computed relative
    to real "now" instead.
    """
    return (dt_util.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


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


async def test_sensor_name_resolves_via_translation(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """The entity name resolves through translation_key/placeholders, not _attr_name."""
    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state is not None
    assert state.attributes["friendly_name"] == f"{MOCK_ADDRESS} Food Waste"


@pytest.mark.parametrize(
    ("waste_type", "expected_key"),
    [
        ("Food Waste", "food_waste"),
        ("Recycling", "recycling"),
        ("Refuse", "refuse"),
        ("Garden Waste", "garden_waste"),
        ("Household Rubbish", "refuse"),
        ("Bulky Waste", "other"),
        ("Non-recyclable Waste", "refuse"),
        ("Non recyclable Waste", "refuse"),
    ],
)
def test_translation_key_classifies_known_and_unknown_waste_types(
    waste_type: str, expected_key: str
) -> None:
    """Known waste-type strings map to a specific icon/name key; others fall back to 'other'."""
    assert _translation_key(waste_type) == expected_key


async def test_icons_are_defined_for_every_translation_key(hass: HomeAssistant) -> None:
    """icons.json has an entry for every translation_key the classifier can produce."""
    icons = await async_get_icons(hass, "entity", integrations={DOMAIN})
    sensor_icons = icons[DOMAIN]["sensor"]
    for expected_key in {"food_waste", "recycling", "garden_waste", "refuse", "other"}:
        assert expected_key in sensor_icons
        assert sensor_icons[expected_key]["default"].startswith("mdi:")


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


async def test_rename_within_same_category_keeps_entity_identity(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """A council rename that keeps the same kind of waste keeps the same entity.

    "Food Waste" -> "Food Waste (Weekly Collection)" still classifies as
    food_waste, so the sensor should keep its unique_id and stay available
    with the updated date, rather than the old entity going unavailable and
    a new one being created.
    """
    coordinator = loaded_entry.runtime_data
    food_waste, recycling, refuse = MOCK_SCHEDULE.collections
    new_date = food_waste.next_collection + timedelta(days=7)
    coordinator.async_set_updated_data(
        replace(
            MOCK_SCHEDULE,
            collections=[
                replace(
                    food_waste,
                    waste_type="Food Waste (Weekly Collection)",
                    next_collection=new_date,
                ),
                recycling,
                refuse,
            ],
        )
    )
    await hass.async_block_till_done()

    entity_id = _entity_id(hass, "food_waste")
    assert entity_id == "sensor.lewisham_council_bins_food_waste"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == str(new_date)

    ent_reg = er.async_get(hass)
    assert ent_reg.async_get(entity_id).unique_id == f"{MOCK_UPRN}_food_waste"


async def test_sibling_stream_disappearing_does_not_affect_unrelated_sensor(
    hass: HomeAssistant,
) -> None:
    """A same-category sibling disappearing must not affect an unrelated sensor.

    Two streams that share a translation key ("Recycling (blue bin)" and
    "Recycling (green bin)", both "recycling") are ambiguous at setup, so
    each gets a slug-based identity key. If one later disappears, the
    survivor's own name is unchanged, so it must keep resolving via the
    exact-name match in `_current_entry` rather than going unavailable just
    because the category is no longer ambiguous among the remaining streams.
    """
    food_waste, recycling, refuse = MOCK_SCHEDULE.collections
    recycling_blue = replace(recycling, waste_type="Recycling (blue bin)")
    recycling_green = replace(recycling, waste_type="Recycling (green bin)")
    initial_schedule = replace(
        MOCK_SCHEDULE,
        collections=[food_waste, recycling_blue, recycling_green, refuse],
    )

    entry = build_mock_entry()
    entry.add_to_hass(hass)

    mock_service = AsyncMock()
    mock_service.get_collection_schedule.return_value = initial_schedule

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

    ent_reg = er.async_get(hass)
    blue_entity_id = ent_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{MOCK_UPRN}_recycling_blue_bin"
    )
    assert blue_entity_id is not None
    assert hass.states.get(blue_entity_id).state != "unavailable"

    coordinator = entry.runtime_data
    coordinator.async_set_updated_data(
        replace(initial_schedule, collections=[food_waste, recycling_blue, refuse])
    )
    await hass.async_block_till_done()

    state = hass.states.get(blue_entity_id)
    assert state is not None
    assert state.state != "unavailable"
    assert ent_reg.async_get(blue_entity_id).unique_id == f"{MOCK_UPRN}_recycling_blue_bin"


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

    midnight = _next_local_midnight()
    before_midnight = midnight - timedelta(hours=12)

    food_waste, recycling, refuse = MOCK_SCHEDULE.collections
    coordinator.async_set_updated_data(
        replace(
            MOCK_SCHEDULE,
            collections=[replace(food_waste, next_collection=midnight.date()), recycling, refuse],
        )
    )

    with patch("homeassistant.util.dt.now", return_value=before_midnight):
        coordinator.async_update_listeners()
        await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state.attributes["collection_in"] == "tomorrow"

    with patch("homeassistant.util.dt.now", return_value=midnight):
        async_fire_time_changed(hass, midnight)
        await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "food_waste"))
    assert state.attributes["days_until_collection"] == 0
    assert state.attributes["collection_in"] == "today"
    assert get_schedule.await_count == calls_before_midnight


async def test_expired_collection_refreshes_at_midnight(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """An expired cached date should trigger one refresh instead of reporting -1."""
    coordinator = loaded_entry.runtime_data
    get_schedule = coordinator.service.get_collection_schedule
    coordinator.update_interval = None
    coordinator._async_unsub_refresh()

    midnight = _next_local_midnight()
    collection_day = midnight - timedelta(hours=12)

    food_waste, recycling, refuse = MOCK_SCHEDULE.collections
    expired_schedule = replace(
        MOCK_SCHEDULE,
        collections=[
            food_waste,
            replace(recycling, next_collection=collection_day.date()),
            refuse,
        ],
    )
    refreshed_schedule = replace(
        expired_schedule,
        collections=[
            replace(food_waste, next_collection=collection_day.date() + timedelta(days=7)),
            replace(recycling, next_collection=midnight.date() + timedelta(days=13)),
            refuse,
        ],
    )
    get_schedule.return_value = refreshed_schedule

    with patch("homeassistant.util.dt.now", return_value=collection_day):
        coordinator.async_set_updated_data(expired_schedule)
        await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, "recycling"))
    assert state.attributes["collection_in"] == "today"
    calls_before_midnight = get_schedule.await_count
    coordinator._debounced_refresh.async_cancel()

    with (
        patch("homeassistant.util.dt.now", return_value=midnight),
        patch.object(
            coordinator,
            "async_request_refresh",
            wraps=coordinator.async_request_refresh,
        ) as request_refresh,
    ):
        async_fire_time_changed(hass, midnight)
        await hass.async_block_till_done()

    request_refresh.assert_awaited_once_with()
    state = hass.states.get(_entity_id(hass, "recycling"))
    assert state.state == str(midnight.date() + timedelta(days=13))
    assert state.attributes["days_until_collection"] == 13
    assert state.attributes["collection_in"] == "13 days"
    assert get_schedule.await_count == calls_before_midnight + 1


def test_sensor_without_coordinator_data_is_unavailable(hass: HomeAssistant) -> None:
    """A sensor is unavailable and has no value or attributes before data exists."""
    entry = build_mock_entry()
    coordinator = LewishamUpdateCoordinator(
        hass,
        entry,
        AsyncMock(),
    )
    sensor = LewishamCollectionSensor(coordinator, MOCK_SCHEDULE.collections[0], "food_waste")

    assert sensor.native_value is None
    assert sensor.available is False
    assert sensor.extra_state_attributes == {}
