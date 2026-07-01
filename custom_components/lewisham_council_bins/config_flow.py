"""Config flow for the Lewisham Council integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.httpx_client import get_async_client
from lewisham_client import (
    AddressCandidate,
    DomainError,
    InvalidAddressSearchError,
    LewishamClient,
    LewishamService,
    UpstreamUnavailableError,
)

from .const import CONF_ADDRESS, CONF_UPRN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required("query"): str})


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
                client = LewishamClient(http_client=get_async_client(self.hass))
                service = LewishamService(
                    client=client,
                    schedule_cache_ttl=timedelta(0),
                    negative_cache_ttl=timedelta(0),
                )
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
        """Handle address selection: store the UPRN as the unique config-entry id."""
        if user_input is not None:
            uprn = user_input[CONF_UPRN]
            candidate = next(c for c in self._candidates if c.uprn == uprn)
            await self.async_set_unique_id(uprn)
            self._abort_if_unique_id_configured()
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
        )
