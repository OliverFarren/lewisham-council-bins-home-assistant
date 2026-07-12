"""Guard against a regression to library-configured/leaked logging.

lewisham-council-client 0.2.0 depended on structlog and, in a process that
never configured structlog (such as Home Assistant), fell back to printing
routine DEBUG/INFO/WARNING events directly to stdout. That bypassed HA's
logging controls and duplicated the coordinator's own failure reporting
during setup retries and refreshes.

0.3.0 uses plain stdlib `logging` and configures no handlers, formatters, or
process-wide levels, so it defers entirely to whatever the host (here, Home
Assistant) does with the `lewisham_client` logger hierarchy. These tests
exercise the *real* client/service/parser stack (over a mocked HTTP
transport, never real network) so a regression to structlog-style
fallback printing would actually be caught: a mocked-out service would let
these events fire silently without a single line of client code running.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from homeassistant.core import HomeAssistant
from lewisham_client import LewishamClient, LewishamParser, LewishamService

from custom_components.lewisham_council_bins.coordinator import LewishamUpdateCoordinator

from .conftest import MOCK_ADDRESS, MOCK_UPRN

_CLIENT_LOGGER_NAMES = [
    "lewisham_client.clients.lewisham.client",
    "lewisham_client.clients.lewisham.parser",
    "lewisham_client.services.lewisham_service",
]

# A minimal fragment the real LewishamParser accepts, mirroring the client
# package's own parser tests: weekly food waste/recycling plus a fortnightly
# refuse entry with an explicit next-collection date.
_SCHEDULE_HTML = """
<h2>When your bins are collected:</h2>
<strong>Food waste</strong>&nbsp;is collected
<span class="RoundsTransform">WEEKLY</span> on Monday.
<br><br>
<strong>Recycling</strong>&nbsp;is collected
<span class="RoundsTransform">WEEKLY</span> on Monday.
<br><br>
<strong>Refuse</strong>&nbsp;is collected
<span class="RoundsTransform">FORTNIGHTLY</span> on Monday.
Your next collection date is 07/07/2026.
"""
_SCHEDULE_BODY = json.dumps(_SCHEDULE_HTML)


def _success_transport() -> httpx.MockTransport:
    """A transport answering both AddressFinder and roundsinformation calls."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "AddressFinder" in request.url.path:
            return httpx.Response(200, json={"Uprn": MOCK_UPRN, "Title": MOCK_ADDRESS})
        return httpx.Response(200, text=_SCHEDULE_BODY)

    return httpx.MockTransport(handler)


def _failing_transport() -> httpx.MockTransport:
    """A transport that fails every request the way a real outage would."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    return httpx.MockTransport(handler)


def _build_coordinator(
    hass: HomeAssistant, transport: httpx.MockTransport
) -> LewishamUpdateCoordinator:
    http_client = httpx.AsyncClient(transport=transport)
    client = LewishamClient(http_client=http_client)
    service = LewishamService(client=client, parser=LewishamParser())
    return LewishamUpdateCoordinator(hass, service, MOCK_UPRN, MOCK_ADDRESS)


@pytest.mark.parametrize("logger_name", _CLIENT_LOGGER_NAMES)
def test_client_loggers_defer_to_host(logger_name: str) -> None:
    """The client must not attach its own handlers or stop propagation.

    A library that installs a handler or disables propagation is choosing its
    own output destination instead of letting the host (Home Assistant)
    decide. Both would recreate the structlog fallback-output problem with
    plain `logging` instead.
    """
    logger = logging.getLogger(logger_name)

    assert logger.handlers == []
    assert logger.propagate is True


async def test_successful_refresh_writes_nothing_to_console(
    hass: HomeAssistant,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful refresh runs real client code but prints nothing.

    Enabling DEBUG on the client loggers maximises the chance that a
    regression to unconfigured structlog fallback output would surface: the
    original bug printed DEBUG events regardless of host log-level
    configuration.
    """
    caplog.set_level(logging.DEBUG, logger="lewisham_client")

    coordinator = _build_coordinator(hass, _success_transport())
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data is not None
    assert any(record.name.startswith("lewisham_client") for record in caplog.records)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


async def test_failed_refresh_writes_nothing_to_console(
    hass: HomeAssistant,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed refresh reports via UpdateFailed/HA's log-once behaviour only.

    Before the 0.3.0 fix, the client itself logged the transport failure
    (via structlog's stdout fallback) before raising it, so the same failure
    was reported twice: once by the client, once by the coordinator's own
    unavailable/recovered tracking. Running the real client against a
    transport that raises a genuine httpx.ConnectError, and asserting
    silence, demonstrates the coordinator is the sole visible reporter of
    this failure.
    """
    caplog.set_level(logging.DEBUG, logger="lewisham_client")

    coordinator = _build_coordinator(hass, _failing_transport())
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert any(
        record.name == "lewisham_client.clients.lewisham.client"
        and record.getMessage() == "upstream_transport_error"
        for record in caplog.records
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
