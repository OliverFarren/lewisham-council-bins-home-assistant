"""Config flow for the Lewisham Council integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from lewisham_client import (
    AddressCandidate,
    AddressNotFoundError,
    CollectionScheduleNotFoundError,
    DomainError,
    InvalidAddressSearchError,
    InvalidUprnError,
    LewishamClient,
    LewishamService,
    UpstreamUnavailableError,
)

from .const import CONF_ADDRESS, CONF_UPRN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required("query"): str})


def _build_service(hass: HomeAssistant) -> LewishamService:
    """Build a LewishamService with caching disabled, for use during the config flow.

    Both flow steps need a fresh, uncached view of upstream state (address
    search, then schedule validation), so caching would only risk masking a
    stale result during setup.
    """
    client = LewishamClient(http_client=get_async_client(hass))
    return LewishamService(
        client=client,
        schedule_cache_ttl=timedelta(0),
        negative_cache_ttl=timedelta(0),
    )


class LewishamCouncilBinsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Lewisham Council integration.

    Step 1 (user): enter a postcode or street name and resolve a candidate list.
    Step 2 (select): pick one address; its UPRN becomes the config-entry unique id.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._candidates: list[AddressCandidate] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step: search for an address by postcode or street."""
        errors: dict[str, str] = {}

        if user_input is not None:
            query = user_input["query"].strip()
            try:
                service = _build_service(self.hass)
                candidates = await service.lookup_addresses(query)
                if not candidates:
                    errors["query"] = "no_addresses_found"
                else:
                    self._candidates = candidates
                    return await self.async_step_select()
            except InvalidAddressSearchError:
                errors["query"] = "invalid_query"
            except UpstreamUnavailableError:
                errors["base"] = "cannot_connect"
            except DomainError:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_select(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle address selection: store the UPRN as the unique config-entry id.

        Checks for an already-configured duplicate first, since that needs no
        network access and shouldn't be masked by an unrelated connectivity
        error. Only then confirms the selected UPRN actually has a collection
        schedule (test-before-configure), rather than leaving the user with an
        entry that only discovers the problem on first refresh. The fetched
        schedule is stashed in hass.data so async_setup_entry can seed the
        coordinator with it instead of fetching the same schedule again
        immediately after entry creation.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            uprn = user_input[CONF_UPRN]
            try:
                candidate = next(c for c in self._candidates if c.uprn == uprn)
            except StopIteration:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(uprn)
                self._abort_if_unique_id_configured()

                service = _build_service(self.hass)
                try:
                    schedule = await service.get_collection_schedule(uprn)
                except (CollectionScheduleNotFoundError, AddressNotFoundError):
                    errors["base"] = "no_schedule"
                except InvalidUprnError:
                    # The address-search step just handed us this UPRN, so
                    # the client rejecting it here signals a mismatch between
                    # the two endpoints, not "no schedule for this address".
                    _LOGGER.error(
                        "Address search returned UPRN %s which was then rejected as invalid",
                        uprn,
                    )
                    errors["base"] = "unknown"
                except UpstreamUnavailableError:
                    errors["base"] = "cannot_connect"
                except DomainError:
                    errors["base"] = "unknown"
                else:
                    self.hass.data.setdefault(DOMAIN, {})[uprn] = schedule
                    return self.async_create_entry(
                        title=candidate.title,
                        data={
                            CONF_UPRN: uprn,
                            CONF_ADDRESS: candidate.title,
                        },
                    )

        options = {c.uprn: c.title for c in self._candidates}
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema({vol.Required(CONF_UPRN): vol.In(options)}),
            errors=errors,
        )
