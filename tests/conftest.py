"""Shared fixtures for Lewisham Council integration tests."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from lewisham_client import AddressCandidate, CollectionEntry, CollectionSchedule
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lewisham_council_bins.const import CONF_ADDRESS, CONF_UPRN, DOMAIN

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable discovery of custom_components/ in all tests."""


MOCK_UPRN = "100021882853"
MOCK_ADDRESS = "1 Test Street, Lewisham, SE13 1AA"

MOCK_CANDIDATES: list[AddressCandidate] = [
    AddressCandidate(uprn=MOCK_UPRN, title=MOCK_ADDRESS),
    AddressCandidate(uprn="100021882854", title="2 Test Street, Lewisham, SE13 1AA"),
]

MOCK_SCHEDULE = CollectionSchedule(
    uprn=MOCK_UPRN,
    address=MOCK_ADDRESS,
    collections=[
        CollectionEntry(
            waste_type="Food Waste",
            frequency="WEEKLY",
            day="Monday",
            next_collection=date(2026, 7, 7),
            next_collection_basis="published",
        ),
        CollectionEntry(
            waste_type="Recycling",
            frequency="FORTNIGHTLY",
            day="Monday",
            next_collection=date(2026, 7, 14),
            next_collection_basis="published",
        ),
        CollectionEntry(
            waste_type="Refuse",
            frequency="FORTNIGHTLY",
            day="Monday",
            next_collection=None,
            next_collection_basis=None,
        ),
    ],
    source_url="https://lewisham.gov.uk/myservices/recycling-and-rubbish/collection-day",
    fetched_at=datetime(2026, 6, 28, 12, 0, 0),
)


def build_mock_entry(uprn: str = MOCK_UPRN, address: str = MOCK_ADDRESS) -> MockConfigEntry:
    """Return a MockConfigEntry shaped like a real Lewisham Council entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_UPRN: uprn, CONF_ADDRESS: address},
        unique_id=uprn,
    )
