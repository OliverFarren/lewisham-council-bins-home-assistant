<p align="center">
  <img
    src="custom_components/lewisham_council_bins/brand/icon.png"
    alt="Lewisham Council Bin Collections"
    width="96"
  />
</p>

# Lewisham Council Bin Collections — Home Assistant Integration

[![Test](https://github.com/OliverFarren/lewisham-council-bins-home-assistant/actions/workflows/test.yml/badge.svg)](https://github.com/OliverFarren/lewisham-council-bins-home-assistant/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/OliverFarren/lewisham-council-bins-home-assistant/branch/main/graph/badge.svg)](https://codecov.io/gh/OliverFarren/lewisham-council-bins-home-assistant)

A [HACS](https://hacs.xyz) custom integration that adds waste collection
schedule sensors for Lewisham addresses to Home Assistant.

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

## Installation via HACS

1. Add this repository as a custom repository in HACS (category: Integration).
2. Install **Lewisham Council Bin Collections**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add integration** and search for
   *Lewisham Council Bin Collections*.

## Manual installation

Copy `custom_components/lewisham_council_bins/` into your HA `custom_components/`
directory and restart Home Assistant.

## Requirements

- Home Assistant ≥ 2024.6
- `lewisham-council-client==0.1.0` (installed automatically by HA from
  `manifest.json`)

## Development

```bash
uv sync --group dev
uv run pytest -v
uv run ruff check .
uv run mypy custom_components/lewisham_council_bins/
```

## Licence

MIT — see [LICENSE](LICENSE).
