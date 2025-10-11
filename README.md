Helios EC‑Pro custom integration for Home Assistant

This custom component integrates Helios EC‑Pro ventilation units over a TCP bridge into Home Assistant. It exposes sensors and fan/climate control and writes commands during brief "send slot" windows after pings on the RS‑485 bus.

Note: This project is verified to work with a HELIOS EC 370 pro ventilation system (circa 2012). The RS‑485 interface is provided by a Waveshare RS485‑to‑Ethernet module connected directly to the Helios RJ12 jack used for “Bedienteile” (control panels).

Full documentation: see `helios_pro_ventilation/documentation.md`.

## Features
- Fan control (auto/manual, levels 0–4)
- Temperature sensors (outdoor, extract, exhaust, supply)
- Filter warning as a diagnostic binary sensor
- Debug: one‑shot scan over Helios variables with a single INFO summary + file exports

## Installation

Manual install (short and complete)

- Download the latest release ZIP from GitHub (or clone this repository).
- Copy the folder `helios_pro_ventilation` into your Home Assistant config's custom components folder so the final path is:
	`config/custom_components/helios_pro_ventilation`
- Restart Home Assistant.
- In Home Assistant: Settings → Devices & Services → Add Integration → “Helios EC‑Pro”.

Default connection: host `192.168.0.51`, port `8234`. You can change these during the UI setup, or by a one‑time YAML import.

## Configuration
The integration supports import from YAML for initial setup. Put this in your Home Assistant `configuration.yaml` and restart once to import defaults:

```yaml
helios_pro_ventilation:
	host: 192.168.0.51
	port: 8234
```

It then creates a config entry in the UI for ongoing management.

## Entities
- Climate (fan control)
- Fan (percentage control 0–100 mapped to levels 0–4; presets auto/manual)
- Select: Lüfterstufe (Auswahl) — options [0..4] mapped to fan levels
- Binary sensors:
	- filter warning (diagnostic)
	- Partymodus aktiv (derived from Var 0x10)
	- Externer Kontakt (Var 0x14)
- Sensors:
	- fan_level (from broadcast; mirrors Var 0x35)
	- Temperatures (Var 0x3A): temp_outdoor, temp_extract, temp_exhaust, temp_supply (°C)
	- Party verbleibend (min) (Var 0x10)
	- Party Zeit (Vorauswahl) (Var 0x11)
	- Bypass Temperatur 1 (Var 0x1E), Bypass Temperatur 2 (Var 0x60)
	- Frostschutz Temperatur (Var 0x1F)
	- Betriebsstunden (Var 0x15)
	- Minimale Lüfterstufe (Var 0x37)
	- Filterwechsel (Monate) (Var 0x38; diagnostic)
	- Party/Zuluft/Abluft Lüfterstufen (Var 0x42/0x45/0x46)
	- Stufe 1–4 Spannungen Zuluft/Abluft (Var 0x16..0x19)
	- Nachlaufzeit (Sekunden) (Var 0x49)
	- Software Version (Var 0x48)
	- Datum / Uhrzeit (Var 0x07 / 0x08)
- Switch: Debug, one‑shot variable scan (stable id: `switch.helios_ec_pro_variablen_scan_debug`)

## Debug: One‑shot var scan

The integration includes a switch to perform a one‑time scan of all known Helios variables and log their decoded values. This is for diagnostics and development.

- Friendly name: “variablen Scan (debug)”
- How it works: when turned on, it queues read requests for each `HeliosVar` at ≥500 ms intervals. As responses arrive:
	- Per‑variable lines are logged at DEBUG.
	- After completion, a single INFO summary is logged with a table that includes the variable code, name, full response values (with units), and notes from the HeliosVar metadata.
	- The summary is also written to timestamped files: `<config>/helios_scan_summary_YYYYMMDD-HHMMSS.txt` and `.md`.
- Special handling: Var_3A temperatures and fan level (0x35) are included in the summary even if the device doesn’t reply to direct reads (forwarded/synthesized from broadcast data).

Tip: to see the debug lines in the UI, set the integration log level to `info` or `debug` in your Home Assistant `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.helios_pro_ventilation: info  # or "debug" for more detail
```

## Services
- `set_auto_mode` (enabled: boolean)
- `set_fan_level` (level: 0–4)
- `set_party_enabled` (enabled: boolean)

## Troubleshooting
- If entities don’t update, verify the bridge connection and check logs for missing pings.
- If write commands don’t take effect, ensure the bus’s ping window is being detected (send slot opens ~80 ms after ping).
- Clear `__pycache__` and reload the custom component if you’ve updated files but see old behavior.

## Development
- Code is threaded for IO; entity state updates are pushed via the Home Assistant loop.
- Tests included for frame parsing; run with `pytest`.
- A fake TCP bridge is provided in `scripts/fake_helios_bridge.py` for local testing.

## License
MIT — see LICENSE

## Changelog
See CHANGELOG.md

## Optional: Device image on cards
Entities always use the integration endpoint `/api/helios_pro_ventilation/image.png` for their `entity_picture`. That endpoint will serve either:
- a file from your Home Assistant `config/www` folder (preferred filename: `MomoRC_HELIOS_HASS.png`, fallback `helios_ec_pro.png`), or
- a packaged image shipped with the integration if no file is found in `www`.

Ways to provide an image (both filenames supported: `MomoRC_HELIOS_HASS.png` or `helios_ec_pro.png`):
- Place it under `config/www/` (recommended for easy customization)
- Or place it in `custom_components/helios_pro_ventilation/`

Tip: After adding/changing the file, reload the integration or restart Home Assistant, and refresh your browser cache.

Note: The Integrations dashboard tile uses brand icons and will not display this image. Use Lovelace cards (below) or an entity info dialog to see it.

## Lovelace examples: Climate and Fan
Below are minimal, ready-to-copy examples showing the picture in standard cards and exposing common controls. Replace the entity ids with the ones from your system (for example `climate.helios_luftung` and `fan.helios_lufter`).

### Picture Entity (Climate)
```yaml
type: picture-entity
entity: climate.helios_luftung  # adjust to your entity id
name: Helios EC-Pro
show_state: true
show_name: true
```

### Tile (Climate) with presets and fan modes
Requires HA 2023.12+ for tile features.
```yaml
type: tile
entity: climate.helios_luftung  # adjust to your entity id
show_entity_picture: true
features:
	- type: climate-hvac-modes
		hvac_modes:
			- off
			- fan_only
	- type: climate-preset-modes
	- type: climate-fan-modes
```

### Tile (Fan) with speed and preset
```yaml
type: tile
entity: fan.helios_lufter  # adjust to your entity id
show_entity_picture: true
features:
	- type: fan-speed
	- type: fan-preset-mode
```

### Quick action buttons (optional)
Manual and Auto presets via buttons:
```yaml
type: horizontal-stack
cards:
	- type: button
		name: Manual
		icon: mdi:hand-back-right
		tap_action:
			action: call-service
			service: climate.set_preset_mode
			target: { entity_id: climate.helios_luftung }
			data: { preset_mode: manual }
	- type: button
		name: Auto
		icon: mdi:robot
		tap_action:
			action: call-service
			service: climate.set_preset_mode
			target: { entity_id: climate.helios_luftung }
			data: { preset_mode: auto }
```

Set level 0–4 via Climate fan_mode:
```yaml
type: grid
columns: 5
cards:
	- type: button
		name: 0
		tap_action:
			action: call-service
			service: climate.set_fan_mode
			target: { entity_id: climate.helios_luftung }
			data: { fan_mode: "0" }
	- type: button
		name: 1
		tap_action:
			action: call-service
			service: climate.set_fan_mode
			target: { entity_id: climate.helios_luftung }
			data: { fan_mode: "1" }
	- type: button
		name: 2
		tap_action:
			action: call-service
			service: climate.set_fan_mode
			target: { entity_id: climate.helios_luftung }
			data: { fan_mode: "2" }
	- type: button
		name: 3
		tap_action:
			action: call-service
			service: climate.set_fan_mode
			target: { entity_id: climate.helios_luftung }
			data: { fan_mode: "3" }
	- type: button
		name: 4
		tap_action:
			action: call-service
			service: climate.set_fan_mode
			target: { entity_id: climate.helios_luftung }
			data: { fan_mode: "4" }
```

## Roadmap / TODO
See TODO.md for planned fixes and improvements.
