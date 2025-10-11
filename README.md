Helios EC‑Pro custom integration for Home Assistant

This custom component integrates Helios EC‑Pro ventilation units over a TCP bridge into Home Assistant. It exposes sensors and climate control and writes commands during brief "send slot" windows after pings on the RS‑485 bus.

## Features
- Fan control (auto/manual, levels 0–4)
- Temperature sensors (outdoor, extract, exhaust, supply)
- Filter warning as a diagnostic binary sensor
- Debug: one‑shot scan over Helios variables with a single INFO summary + file exports

## Installation
1. Copy this repository into Home Assistant's `custom_components/helios_pro_ventilation` directory.
2. Restart Home Assistant, then add the integration via the UI (or keep your existing entry).

Default connection: host `192.168.0.51`, port `8234`. You can change these in the integration config (YAML import or UI).

## Configuration
The integration supports import from YAML for initial setup:

```yaml
helios_pro_ventilation:
	host: 192.168.0.51
	port: 8234
```

It then creates a config entry in the UI for ongoing management.

## Entities
- Climate (fan control)
- Sensors: fan level, temp_outdoor, temp_extract, temp_exhaust, temp_supply
- Binary sensor: filter warning
- Switch: Debug, one‑shot variable scan (stable id: `switch.helios_ec_pro_variablen_scan_debug`)

## Debug: One‑shot var scan

The integration includes a switch to perform a one‑time scan of all known Helios variables and log their decoded values. This is for diagnostics and development.

- Friendly name: “variablen Scan (debug)”
- How it works: when turned on, it queues read requests for each `HeliosVar` at ≥500 ms intervals. As responses arrive:
	- Per‑variable lines are logged at DEBUG.
	- After completion, a single INFO summary is logged with a table that includes the variable code, name, full response values (with units), and notes from the HeliosVar metadata.
	- The summary is also written to timestamped files: `<config>/helios_scan_summary_YYYYMMDD-HHMMSS.txt` and `.md`.
- Special handling: Var_3A temperatures and fan level (0x35) are included in the summary even if the device doesn’t reply to direct reads (forwarded/synthesized from broadcast data).

Tip: to see the debug lines in the UI, set the integration log level to info or debug:

```yaml
logger:
	default: warning
	logs:
		custom_components.helios_pro_ventilation: info
```

## Services
- `set_auto_mode` (enabled: boolean)
- `set_fan_level` (level: 0–4)

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
