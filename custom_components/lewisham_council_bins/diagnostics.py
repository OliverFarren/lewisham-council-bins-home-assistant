"""Diagnostics support for Lewisham Council waste collection schedules.

Beyond the standard config-entry snapshot, this surfaces two things specific
to a scraper-backed integration: CollectionSchedule.data_quality() (how many
streams have a council-published date vs. a weekday-derived guess), and —
only when the last refresh failed — the upstream contract-drift diagnostics
the lewisham-council-client library attaches to its exceptions (payload
hash/size and, if opted in, a raw-payload preview, found via
find_diagnostics() and scrubbed here of the UPRN/address before inclusion).
That is the detail a maintainer actually needs to fix a broken parser when
Lewisham changes their page. Both helpers are owned by lewisham_client, not
duplicated here, since they only depend on its own domain types.
"""

from __future__ import annotations

import dataclasses
import re
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.loader import async_get_integration
from lewisham_client import CollectionSchedule, ContractDriftDiagnostics, find_diagnostics

from .const import CONF_ADDRESS, CONF_UPRN, DOMAIN
from .coordinator import LewishamCouncilBinsConfigEntry

TO_REDACT = {
    CONF_UPRN,
    CONF_ADDRESS,
    "uprn",
    "address",
    "title",
    "unique_id",
    "name",
    "friendly_name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LewishamCouncilBinsConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    # HA's UpdateFailed renders its translation placeholders into the message
    # text (see coordinator.py's schedule_not_found branch, which passes
    # uprn=), so any exception message must be scrubbed, not just the
    # upstream_diagnostics payload preview.
    secrets = [entry.data[CONF_UPRN], *_address_parts(entry.data[CONF_ADDRESS])]

    diagnostics: dict[str, Any] = {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_success_time": _isoformat(coordinator.last_update_success_time),
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval is not None
                else None
            ),
            "last_exception": _describe_exception(coordinator.last_exception, secrets),
        },
        "versions": {
            "integration": str((await async_get_integration(hass, DOMAIN)).version),
            "lewisham_council_client": _client_library_version(),
        },
    }

    if coordinator.data is not None:
        diagnostics["data"] = _serialize_schedule(coordinator.data)
        diagnostics["data_quality"] = dataclasses.asdict(coordinator.data.data_quality())

    if not coordinator.last_update_success and coordinator.last_exception is not None:
        drift = find_diagnostics(coordinator.last_exception)
        if drift is not None:
            diagnostics["upstream_diagnostics"] = _serialize_drift_diagnostics(drift, secrets)

    return diagnostics


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: LewishamCouncilBinsConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    # Built explicitly rather than from device.dict_repr: "identifiers" embeds
    # the UPRN as a bare string inside a list of tuples, which async_redact_data's
    # key-based redaction cannot reach.
    diagnostics["device"] = async_redact_data(
        {
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version,
            "hw_version": device.hw_version,
            "disabled_by": device.disabled_by,
            "entry_type": device.entry_type,
        },
        TO_REDACT,
    )

    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_device(
        entity_registry, device.id, include_disabled_entities=True
    )
    entity_diagnostics: list[dict[str, Any]] = []
    for registry_entry in entities:
        state = hass.states.get(registry_entry.entity_id)
        entity_diagnostics.append(
            async_redact_data(
                {
                    "entity_id": registry_entry.entity_id,
                    "state": state.state if state is not None else None,
                    "attributes": dict(state.attributes) if state is not None else None,
                },
                TO_REDACT,
            )
        )
    diagnostics["entities"] = entity_diagnostics

    return diagnostics


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _describe_exception(error: BaseException | None, secrets: list[str]) -> dict[str, str] | None:
    if error is None:
        return None
    return {"type": type(error).__name__, "message": _scrub_secrets(str(error), secrets)}


def _client_library_version() -> str | None:
    try:
        return version("lewisham-council-client")
    except PackageNotFoundError:
        return None


def _serialize_schedule(schedule: CollectionSchedule) -> dict[str, Any]:
    return {
        "source_url": schedule.source_url,
        "fetched_at": schedule.fetched_at.isoformat(),
        "collections": [
            {
                "waste_type": collection.waste_type,
                "frequency": collection.frequency,
                "day": collection.day,
                "next_collection": _isoformat(collection.next_collection),
                "next_collection_basis": collection.next_collection_basis,
            }
            for collection in schedule.collections
        ],
    }


def _address_parts(address: str) -> list[str]:
    return [part.strip() for part in address.split(",") if part.strip()]


# payload_preview is raw, undecoded upstream HTML (see LewishamParser
# _build_drift_diagnostics), so whitespace between the words of an address
# may appear as literal newlines/indentation or as an HTML entity rather
# than a single space. Joining each secret's words with this instead of a
# literal space lets scrubbing survive that without decoding the preview
# itself, which would misrepresent the raw payload a maintainer is trying to
# inspect.
_FLEXIBLE_WHITESPACE = r"(?:\s|&nbsp;|&#0*160;|&#x0*[aA]0;)+"


def _secret_pattern(secret: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in secret.split()]
    return re.compile(_FLEXIBLE_WHITESPACE.join(words), re.IGNORECASE)


def _scrub_secrets(text: str, secrets: list[str]) -> str:
    scrubbed = text
    for secret in secrets:
        if not secret:
            continue
        scrubbed = _secret_pattern(secret).sub("**REDACTED**", scrubbed)
    return scrubbed


def _serialize_drift_diagnostics(
    drift: ContractDriftDiagnostics, secrets: list[str]
) -> dict[str, Any]:
    preview = drift.payload_preview
    if preview is not None:
        preview = _scrub_secrets(preview, secrets)
    return {
        "error_type": drift.error_type,
        "error_message": _scrub_secrets(drift.error_message, secrets),
        "source": drift.source,
        "payload_size_bytes": drift.payload_size_bytes,
        "payload_sha256": drift.payload_sha256,
        "payload_preview": preview,
        "payload_truncated": drift.payload_truncated,
        "status_code": drift.status_code,
        "endpoint": drift.endpoint,
    }
