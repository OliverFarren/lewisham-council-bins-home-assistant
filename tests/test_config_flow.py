"""Tests for the Lewisham Council config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from lewisham_client import (
    AddressNotFoundError,
    CollectionScheduleNotFoundError,
    DomainError,
    InvalidAddressSearchError,
    InvalidUprnError,
    UpstreamUnavailableError,
)

from custom_components.lewisham_council_bins.config_flow import LewishamCouncilBinsConfigFlow
from custom_components.lewisham_council_bins.const import CONF_ADDRESS, CONF_UPRN, DOMAIN

from .conftest import MOCK_ADDRESS, MOCK_CANDIDATES, MOCK_SCHEDULE, MOCK_UPRN, build_mock_entry


def _mock_service(candidates: list = MOCK_CANDIDATES) -> AsyncMock:
    """Return a mock LewishamService whose lookup_addresses returns the given candidates.

    get_collection_schedule defaults to succeeding, since async_step_select now
    validates the selected UPRN before creating the entry.
    """
    service = AsyncMock()
    service.lookup_addresses.return_value = list(candidates)
    service.get_collection_schedule.return_value = MOCK_SCHEDULE
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


async def test_upstream_unavailable_recovers(hass: HomeAssistant) -> None:
    """The flow should recover when address search succeeds on retry."""
    mock_service = AsyncMock()
    mock_service.lookup_addresses.side_effect = [
        UpstreamUnavailableError("timeout"),
        MOCK_CANDIDATES,
    ]
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

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "SE13 1AA"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select"
    assert mock_service.lookup_addresses.await_count == 2


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
    existing = build_mock_entry()
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


async def test_duplicate_uprn_aborts_without_a_schedule_validation_call(
    hass: HomeAssistant,
) -> None:
    """The duplicate check runs before the network validation call, not after it.

    If get_collection_schedule were called first (as it briefly was), an
    upstream outage would surface as "cannot_connect" instead of the correct
    "already configured" abort, hiding the real reason from the user. Making
    the mocked schedule fetch fail proves the abort doesn't depend on it.
    """
    existing = build_mock_entry()
    existing.add_to_hass(hass)

    mock_service = _mock_service()
    mock_service.get_collection_schedule.side_effect = UpstreamUnavailableError("timeout")
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
    mock_service.get_collection_schedule.assert_not_awaited()


async def test_selecting_unknown_uprn_shows_unknown_error(hass: HomeAssistant) -> None:
    """A UPRN absent from the stored candidates (e.g. a stale form) shows unknown, not a crash.

    The dropdown's vol.In(options) normally prevents this, but a stale or
    replayed form submission could still reach the handler directly, so the
    candidate lookup must not raise StopIteration unhandled.
    """
    flow = LewishamCouncilBinsConfigFlow()
    flow.hass = hass
    flow._candidates = list(MOCK_CANDIDATES)

    result = await flow.async_step_select(user_input={CONF_UPRN: "not-a-real-uprn"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select"
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        pytest.param(
            CollectionScheduleNotFoundError("no schedule for uprn"),
            "no_schedule",
            id="schedule_not_found",
        ),
        pytest.param(
            AddressNotFoundError("uprn not found"),
            "no_schedule",
            id="address_not_found",
        ),
        pytest.param(
            InvalidUprnError("malformed uprn"),
            "unknown",
            id="invalid_uprn",
        ),
        pytest.param(
            UpstreamUnavailableError("timeout"),
            "cannot_connect",
            id="upstream_unavailable",
        ),
        pytest.param(
            DomainError("boom"),
            "unknown",
            id="unexpected_domain_error",
        ),
    ],
)
async def test_selecting_address_validates_schedule_before_creating_entry(
    hass: HomeAssistant, side_effect: Exception, expected_error: str
) -> None:
    """The select step surfaces a schedule error instead of creating a broken entry.

    test-before-configure: catching an unsupported UPRN here means the user
    never gets an entry that fails on first refresh with no clear path back
    to address selection.
    """
    mock_service = _mock_service()
    mock_service.get_collection_schedule.side_effect = side_effect
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

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select"
    assert result["errors"] == {"base": expected_error}
    mock_service.get_collection_schedule.assert_awaited_once_with(MOCK_UPRN)


async def test_selecting_address_recovers_after_schedule_validation_failure(
    hass: HomeAssistant,
) -> None:
    """After a schedule-validation failure, retrying the same UPRN can still succeed."""
    mock_service = _mock_service()
    mock_service.get_collection_schedule.side_effect = [
        UpstreamUnavailableError("timeout"),
        MOCK_SCHEDULE,
    ]
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
        assert result["errors"] == {"base": "cannot_connect"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_UPRN: MOCK_UPRN}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UPRN] == MOCK_UPRN
    assert mock_service.get_collection_schedule.await_count == 2


async def test_invalid_uprn_from_client_is_logged_as_an_error(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """InvalidUprnError from a UPRN our own address search just returned is logged for diagnosis.

    This is distinct from "no schedule published for this address": it means
    the client's own validation disagrees with the client's own search
    results, which is worth a maintainer's attention rather than silent
    swallowing behind the generic 'unknown' error shown to the user.
    """
    mock_service = _mock_service()
    mock_service.get_collection_schedule.side_effect = InvalidUprnError("malformed uprn")
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

    assert result["errors"] == {"base": "unknown"}
    assert any(
        record.levelname == "ERROR" and MOCK_UPRN in record.getMessage()
        for record in caplog.records
    )


async def test_successful_setup_reuses_the_schedule_validated_during_config_flow(
    hass: HomeAssistant,
) -> None:
    """Setup right after config-flow entry creation should not refetch the same schedule.

    async_step_select already fetched MOCK_SCHEDULE to validate the UPRN
    before creating the entry (test-before-configure). async_setup_entry
    should reuse that result via the hass.data handoff instead of hitting
    the upstream service a second time for the same schedule.
    """
    mock_service = _mock_service()
    with (
        patch("custom_components.lewisham_council_bins.config_flow.LewishamClient"),
        patch(
            "custom_components.lewisham_council_bins.config_flow.LewishamService",
            return_value=mock_service,
        ),
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
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"query": "SE13 1AA"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_UPRN: MOCK_UPRN}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert mock_service.get_collection_schedule.await_count == 1

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = entry.runtime_data
    assert coordinator.data is MOCK_SCHEDULE
    assert coordinator.last_update_success is True
    assert coordinator.last_update_success_time is not None
