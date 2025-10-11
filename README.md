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
