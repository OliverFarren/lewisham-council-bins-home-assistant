"""Tests for the Lewisham Council config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from lewisham_client import DomainError, InvalidAddressSearchError, UpstreamUnavailableError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lewisham_council_bins.const import CONF_ADDRESS, CONF_UPRN, DOMAIN

from .conftest import MOCK_ADDRESS, MOCK_CANDIDATES, MOCK_UPRN


def _mock_service(candidates: list = MOCK_CANDIDATES) -> AsyncMock:
    """Return a mock LewishamService whose lookup_addresses returns the given candidates."""
    service = AsyncMock()
    service.lookup_addresses.return_value = list(candidates)
    return service


@pytest.fixture(autouse=True)
def _mock_httpx() -> Generator[None]:
    """Patch get_async_client so the config flow never touches real HTTP."""
    with patch(
        "custom_components.lewisham_council_bins.config_flow.get_async_client",
        return_value=MagicMock(),
    ):
        yield


async def test_shows_user_form(hass: HomeAssistant) -> None:
    """The initial step should present the address-search form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_valid_postcode_advances_to_select(hass: HomeAssistant) -> None:
    """A postcode that resolves addresses progresses to the address-selection step."""
    mock_service = _mock_service()
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "SE13 1AA"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select"
    mock_service.lookup_addresses.assert_awaited_once_with("SE13 1AA")


async def test_selecting_address_creates_entry(hass: HomeAssistant) -> None:
    """Confirming an address creates a config entry with UPRN as the unique id."""
    mock_service = _mock_service()
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "SE13 1AA"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_UPRN: MOCK_UPRN}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UPRN] == MOCK_UPRN
    assert result["data"][CONF_ADDRESS] == MOCK_ADDRESS


async def test_no_addresses_found_shows_error(hass: HomeAssistant) -> None:
    """An empty result from the address search shows a no_addresses_found error."""
    mock_service = _mock_service(candidates=[])
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "ZZ99 9ZZ"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"query": "no_addresses_found"}


async def test_upstream_unavailable_shows_cannot_connect(hass: HomeAssistant) -> None:
    """A network failure during address search shows a cannot_connect error."""
    mock_service = AsyncMock()
    mock_service.lookup_addresses.side_effect = UpstreamUnavailableError("timeout")
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "SE13 1AA"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_invalid_query_shows_error(hass: HomeAssistant) -> None:
    """A malformed search query shows an invalid_query error."""
    mock_service = AsyncMock()
    mock_service.lookup_addresses.side_effect = InvalidAddressSearchError("too short")
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "?"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"query": "invalid_query"}


async def test_unexpected_domain_error_shows_unknown(hass: HomeAssistant) -> None:
    """An unanticipated domain error shows a generic unknown error."""
    mock_service = AsyncMock()
    mock_service.lookup_addresses.side_effect = DomainError("boom")
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "SE13 1AA"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_duplicate_uprn_aborts(hass: HomeAssistant) -> None:
    """Attempting to add an already-configured UPRN aborts the flow."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_UPRN: MOCK_UPRN, CONF_ADDRESS: MOCK_ADDRESS},
        unique_id=MOCK_UPRN,
    )
    existing.add_to_hass(hass)

    mock_service = _mock_service()
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "SE13 1AA"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_UPRN: MOCK_UPRN}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
