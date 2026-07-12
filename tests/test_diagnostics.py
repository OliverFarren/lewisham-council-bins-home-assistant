"""Tests for the Lewisham Council diagnostics platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from lewisham_client import (
    CollectionScheduleNotFoundError,
    ContractDriftDiagnostics,
    UpstreamScraperChangedError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.lewisham_council_bins import diagnostics as diagnostics_module
from custom_components.lewisham_council_bins.const import DOMAIN

from .conftest import MOCK_ADDRESS, MOCK_SCHEDULE, MOCK_UPRN, build_mock_entry
from .helpers import get_diagnostics_for_config_entry, get_diagnostics_for_device


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


def _device(hass: HomeAssistant) -> dr.DeviceEntry:
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, MOCK_UPRN)})
    assert device is not None
    return device


async def test_config_entry_diagnostics_redacts_and_reports_success(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    loaded_entry: MockConfigEntry,
) -> None:
    """A healthy entry's diagnostics contain no UPRN/address and a data-quality summary."""
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, loaded_entry)

    dumped = str(diagnostics)
    assert MOCK_UPRN not in dumped
    assert MOCK_ADDRESS not in dumped

    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["last_exception"] is None
    assert diagnostics["data_quality"] == {
        "total_collections": 3,
        "published_count": 2,
        "weekday_derived_count": 0,
        "missing_next_collection_count": 1,
    }
    assert "upstream_diagnostics" not in diagnostics


async def test_config_entry_diagnostics_surfaces_scrubbed_drift_on_failure(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    loaded_entry: MockConfigEntry,
) -> None:
    """A subsequent parse failure surfaces upstream_diagnostics with PII scrubbed."""
    coordinator = loaded_entry.runtime_data
    preview = f"...{MOCK_UPRN}... {MOCK_ADDRESS} ...broken markup"
    drift = ContractDriftDiagnostics(
        error_type="UpstreamScraperChangedError",
        error_message="roundsinformation returned invalid JSON.",
        source="parser",
        payload_size_bytes=len(preview.encode("utf-8")),
        payload_sha256="deadbeef",
        payload_preview=preview,
        payload_truncated=False,
    )
    coordinator.service.get_collection_schedule.side_effect = UpstreamScraperChangedError(
        "roundsinformation returned invalid JSON.", diagnostics=drift
    )

    await coordinator.async_refresh()

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, loaded_entry)

    assert diagnostics["coordinator"]["last_update_success"] is False
    assert diagnostics["coordinator"]["last_exception"]["type"] == "UpdateFailed"

    upstream = diagnostics["upstream_diagnostics"]
    assert upstream["source"] == "parser"
    assert upstream["payload_sha256"] == "deadbeef"
    assert MOCK_UPRN not in upstream["payload_preview"]
    assert MOCK_ADDRESS not in upstream["payload_preview"]
    assert "**REDACTED**" in upstream["payload_preview"]

    # Last-known-good data is still reported alongside the failure.
    assert diagnostics["data"]["collections"][0]["waste_type"] == "Food Waste"


async def test_config_entry_diagnostics_scrubs_address_html_whitespace_variants(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    loaded_entry: MockConfigEntry,
) -> None:
    """Scrubbing must survive the raw HTML formatting a contract-drift preview can contain.

    payload_preview is undecoded upstream HTML, so an address can appear
    with &nbsp; entities or pretty-printed whitespace between words instead
    of the single spaces stored in config entry data. A purely literal
    string match misses those variants and leaks the address.
    """
    coordinator = loaded_entry.runtime_data
    preview = "<td>1&nbsp;Test&nbsp;Street</td>\n<td>Lewisham</td>\n<td>SE13\n      1AA</td>"
    drift = ContractDriftDiagnostics(
        error_type="UpstreamScraperChangedError",
        error_message="roundsinformation returned invalid JSON.",
        source="parser",
        payload_size_bytes=len(preview.encode("utf-8")),
        payload_sha256="deadbeef",
        payload_preview=preview,
        payload_truncated=False,
    )
    coordinator.service.get_collection_schedule.side_effect = UpstreamScraperChangedError(
        "roundsinformation returned invalid JSON.", diagnostics=drift
    )

    await coordinator.async_refresh()

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, loaded_entry)

    upstream_preview = diagnostics["upstream_diagnostics"]["payload_preview"]
    assert "Test" not in upstream_preview
    assert "Street" not in upstream_preview
    assert "SE13" not in upstream_preview
    assert upstream_preview.count("**REDACTED**") == 3


async def test_config_entry_diagnostics_scrubs_uprn_from_update_failed_message(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    loaded_entry: MockConfigEntry,
) -> None:
    """UpdateFailed's 'schedule_not_found' message embeds the raw UPRN.

    On modern HA, strings.json interpolates the translation placeholder; on
    HA before 2024.12, coordinator.py formats the English fallback. This is a
    regression test for both versions of that leak path.
    """
    coordinator = loaded_entry.runtime_data
    coordinator.service.get_collection_schedule.side_effect = CollectionScheduleNotFoundError(
        f"No collection schedule found for UPRN {MOCK_UPRN}."
    )

    await coordinator.async_refresh()

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, loaded_entry)

    assert diagnostics["coordinator"]["last_update_success"] is False
    message = diagnostics["coordinator"]["last_exception"]["message"]
    assert MOCK_UPRN not in message
    assert "**REDACTED**" in message


async def test_config_entry_diagnostics_reports_none_when_client_package_missing(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    loaded_entry: MockConfigEntry,
) -> None:
    """If the client package's own version metadata is unavailable, report None rather than raise.

    importlib.metadata.version() raises PackageNotFoundError when a package's
    distribution metadata can't be found (e.g. an editable/vendored install).
    """
    with patch.object(
        diagnostics_module, "version", side_effect=diagnostics_module.PackageNotFoundError
    ):
        diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, loaded_entry)

    assert diagnostics["versions"]["lewisham_council_client"] is None


def test_scrub_secrets_skips_empty_secrets() -> None:
    """An empty secret (e.g. a blank address part) is skipped rather than matched."""
    assert diagnostics_module._scrub_secrets("some text", ["", "text"]) == "some **REDACTED**"


async def test_device_diagnostics_includes_entities_and_redacts_device_name(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    loaded_entry: MockConfigEntry,
) -> None:
    """Device diagnostics list each sensor's state/attributes and redact the device name."""
    device = _device(hass)
    diagnostics = await get_diagnostics_for_device(hass, hass_client, loaded_entry, device)

    assert diagnostics["device"]["name"] == "**REDACTED**"
    entity_ids = {entity["entity_id"] for entity in diagnostics["entities"]}
    assert "sensor.lewisham_council_bins_food_waste" in entity_ids

    dumped = str(diagnostics)
    assert MOCK_UPRN not in dumped
    assert MOCK_ADDRESS not in dumped
