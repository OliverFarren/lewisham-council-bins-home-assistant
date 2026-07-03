"""Tests for the bundled reminder blueprint."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from homeassistant.components.automation.config import PLATFORM_SCHEMA
from homeassistant.components.blueprint.const import CONF_INPUT, CONF_USE_BLUEPRINT
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.const import CONF_PATH
from homeassistant.util import yaml

BLUEPRINT_PATH = (
    Path(__file__).parents[1]
    / "blueprints"
    / "automation"
    / "lewisham_council_bins"
    / "reminder.yaml"
)


def test_reminder_blueprint_validates_as_an_automation() -> None:
    """The blueprint expands to automation syntax supported by the HA minimum."""
    data = yaml.load_yaml(str(BLUEPRINT_PATH))
    assert data["trigger"][0]["platform"] == "time"

    blueprint_kwargs: dict[str, Any] = {}
    if "schema" in inspect.signature(Blueprint).parameters:
        from homeassistant.components.automation.config import (  # noqa: PLC0415
            AUTOMATION_BLUEPRINT_SCHEMA,
        )

        blueprint_kwargs["schema"] = AUTOMATION_BLUEPRINT_SCHEMA
    blueprint = Blueprint(
        data,
        path=str(BLUEPRINT_PATH),
        expected_domain="automation",
        **blueprint_kwargs,
    )
    instance = {
        CONF_USE_BLUEPRINT: {
            CONF_PATH: str(BLUEPRINT_PATH),
            CONF_INPUT: {
                "bin_sensor": "sensor.test",
                "reminder_time": "20:00:00",
                "notify_action": [
                    {
                        "service": "persistent_notification.create",
                        "data": {"message": "Test"},
                    }
                ],
            },
        }
    }

    expanded = BlueprintInputs(blueprint, instance).async_substitute()
    PLATFORM_SCHEMA(expanded)
