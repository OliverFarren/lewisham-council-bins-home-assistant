<p align="center">
  <img
    src="custom_components/lewisham_council_bins/brand/icon.png"
    alt="Lewisham Council Bin Collections"
    width="96"
  />
</p>

# Lewisham Council Bin Collections — Home Assistant Integration

[![Test](https://github.com/OliverFarren/lewisham-council-bins-home-assistant/actions/workflows/test.yml/badge.svg)](https://github.com/OliverFarren/lewisham-council-bins-home-assistant/actions/workflows/test.yml)
[![Validate](https://github.com/OliverFarren/lewisham-council-bins-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/OliverFarren/lewisham-council-bins-home-assistant/actions/workflows/validate.yml)
[![codecov](https://codecov.io/gh/OliverFarren/lewisham-council-bins-home-assistant/branch/main/graph/badge.svg)](https://codecov.io/gh/OliverFarren/lewisham-council-bins-home-assistant)
[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Latest release](https://img.shields.io/github/v/release/OliverFarren/lewisham-council-bins-home-assistant)](https://github.com/OliverFarren/lewisham-council-bins-home-assistant/releases/latest)

A [HACS](https://hacs.xyz) custom integration that retrieves household waste
collection schedules from [Lewisham Council's bin collection
service](https://lewisham.gov.uk/myservices/recycling-and-rubbish/your-bins/collection)
and adds them to Home Assistant. It is intended for residential addresses in
the London Borough of Lewisham.

This is an unofficial community integration and is not affiliated with or
endorsed by Lewisham Council. It relies on undocumented public endpoints that
may change without notice.

## What it provides

- A two-stage config flow: enter your postcode or street, then select your
  exact address. The UPRN is stored; no re-search is needed on restart.
- One `sensor` per waste stream (Food Waste, Recycling, Refuse) with
  `device_class: date` so the next collection date displays cleanly on
  dashboards.
- Attributes on each sensor: `frequency`, `day`, `next_collection_basis`,
  `days_until_collection` (integer), and `collection_in` (e.g. `"today"`,
  `"tomorrow"`, `"4 days"`).
- Clean entity IDs: `sensor.lewisham_council_bins_food_waste` etc. — not tied to the
  address string.
- A single device per address, grouped in the HA device registry.
- Automatic polling every 12 hours via HA's shared coordinator pattern.

## Prerequisites

- Home Assistant 2024.6 or newer.
- For the recommended installation method, a working
  [HACS](https://www.hacs.xyz/docs/use/) installation.

## Installation

### HACS (recommended)

1. In HACS, open the three-dot menu and select **Custom repositories**.
2. Enter
   `https://github.com/OliverFarren/lewisham-council-bins-home-assistant`,
   select **Integration** as the category, and select **Add**.
3. Find **Lewisham Council Bin Collections** in HACS and select **Download**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services** and select **Add integration**.
6. Search for and select **Lewisham Council Bin Collections**.
7. Enter a Lewisham postcode or street, select the matching address, and
   complete the setup.

### Manual installation

1. Copy `custom_components/lewisham_council_bins/` from this repository into
   the `custom_components/` directory in your Home Assistant configuration
   directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services** and select **Add integration**.
4. Search for and select **Lewisham Council Bin Collections**.
5. Enter a Lewisham postcode or street, select the matching address, and
   complete the setup.

## Removal

1. Go to **Settings → Devices & services** and select
   **Lewisham Council Bin Collections**.
2. Open the three-dot menu for the address you want to remove and select
   **Delete**.
3. To uninstall the custom integration as well, remove it through HACS. For a
   manual installation, delete the
   `custom_components/lewisham_council_bins/` directory instead.
4. Restart Home Assistant after uninstalling the custom integration files.


## Development

```bash
uv sync --group dev
uv run pytest -v
uv run ruff check .
uv run mypy custom_components/lewisham_council_bins/
```

## Licence

MIT — see [LICENSE](LICENSE).
