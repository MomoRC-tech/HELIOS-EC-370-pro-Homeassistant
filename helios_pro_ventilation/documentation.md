# Helios EC‑Pro Home Assistant Integration — Full Documentation

This document provides a complete overview of the custom integration, including the system concept, hardware hookup, networking, Home Assistant interface, background operation, diagnostics, troubleshooting, and developer notes.

## 1. Concept and scope

- Goal: Control and monitor a Helios EC‑Pro ventilation unit locally from Home Assistant (HA) using an RS‑485 to Ethernet bridge.
- Approach: A “local_push” HA integration that listens to broadcast frames from the Helios bus and performs writes/reads inside short send windows after a ping is observed on the bus.
- Transport: TCP connection to an RS‑485 ↔ Ethernet bridge (tested with a Waveshare module).
- Protocol: Simple byte frames with a checksum; device variables (HeliosVar) are read/written by index with fixed-width payloads.

Important: This project is verified to work with a Helios EC 370 pro ventilation system manufactured around 2012, using a Waveshare RS‑485 to Ethernet module connected directly to the Helios RJ12 “Bedienteil” port. Other devices or years may differ.

## 2. Architecture overview

The integration package is `custom_components/helios_pro_ventilation` and consists of:
- `__init__.py` — lifecycle, config entry import, service registration, and wiring of the coordinator and IO reader threads.
- `broadcast_listener.py` — threaded network IO: reads raw bus frames over TCP, parses them, updates the coordinator, and drains the TX queue during send slots; schedules periodic reads.
- `parser.py` — parsing helpers for broadcast frames, Var_3A temperature frames, generic variable frames, ping detection, and checksum.
- `coordinator.py` — central in‑memory state store; keeps entity list, queues TX frames, builds write frames; exposes methods used by entities and services.
- Entity platforms — expose data and controls in HA:
	- `climate.py` — Fan‑only climate entity with presets (manual/auto) and fan levels.
	- `fan.py` — Native Fan entity with percentage and preset control.
	- `sensor.py` — Numeric and text sensors for temperatures, hours, levels, version, date/time, etc.
	- `binary_sensor.py` — Filter warning, party enabled, external contact.
	- `select.py` — Fan level select (0..4).
	- `switch.py` — Diagnostic “one‑shot variable scan”.
- `debug_scanner.py` — Implements the one‑shot scan with aggregated summary logs and file exports.
- `const.py` — The `HeliosVar` index map with metadata (bit width, count, units, scaling, access, note).

Data flow
- Incoming: Broadcast frames and variable reads are parsed and merged into `coordinator.data`. Entities are notified via HA’s event loop (`async_write_ha_state`).
- Outgoing: Writes are queued in `coordinator.tx_queue` and sent during a short “send slot” (~80 ms) after a bus ping; a background sender thread drains the queue.
- Polling: A lightweight scheduler in the listener periodically requests key variables (e.g., temperatures every 30s; hourly housekeeping reads). Party current time (Var 0x10) is polled dynamically (10 min while active, else hourly).

## 3. Hardware and wiring

Tested equipment
- Helios EC 370 pro (circa 2012).
- Waveshare RS‑485 ↔ Ethernet module (configured as TCP server).

Wiring
- Connect the Waveshare RS‑485 to the Helios RJ12 port used for “Bedienteile” (control panels). Ensure wiring polarity matches the RS‑485 A/B lines. Use an appropriate RJ12 breakout or cable. Keep cable lengths reasonable and follow RS‑485 best practices.

Electrical safety
- You are responsible for safe wiring. Miswiring can damage equipment. Double‑check polarity and pinouts. Disconnect power when making changes.

## 4. Network configuration (Waveshare)

Configure the Waveshare module as a TCP server listening on a fixed IP and port (the integration defaults to `192.168.0.51:8234`).
- Mode: TCP Server
- Local Port: 8234 (or your choice; update the integration settings accordingly)
- IP: Static assignment or DHCP reservation recommended

Home Assistant will act as a TCP client connecting to this host:port.

## 5. Installation (Home Assistant)

Manual install (short and complete)

- Download the latest release archive from GitHub Releases (or clone this repository).
- Copy the folder `helios_pro_ventilation` into your Home Assistant config’s custom integration folder `custom_components` so the final path is:
  `config/custom_components/helios_pro_ventilation`
- Restart Home Assistant.
- Add the integration via Settings → Devices & Services → Add Integration → “Helios EC‑Pro”.
- Optional: Provide YAML once to import default host/port values (the entry will then be managed via the UI). Place this in your Home Assistant `configuration.yaml`:

```yaml
helios_pro_ventilation:
  host: 192.168.0.51
  port: 8234
```

The integration creates a config entry in the UI and starts background threads for IO and scheduling.

## 6. Features

- Local push updates from the RS‑485 bus
- Fan control: auto/manual, levels 0–4
- Entities for temperatures, timers, hours, party/level states, and diagnostics
- Native Fan entity (percentage and presets)
- Fan level Select entity (0..4)
- Services to set auto mode, fan level, and party mode
- Diagnostic one‑shot “variable scan” with logs and file exports

## 7. Home Assistant interface

Entities (selection)
- Climate: “Helios Lüftung” — Fan‑only climate with presets manual/auto; fan modes 0–4.
- Fan: “Helios Lüfter” — Percentage control mapped to levels 0–4 (0/25/50/75/100); presets manual/auto.
- Select: “Lüfterstufe (Auswahl)” — Choose 0..4; maps to set_fan_level.
- Binary sensors:
	- Automatikmodus aktiv (auto_mode)
	- Partymodus aktiv (derived from Var 0x10 current time > 0)
	- Externer Kontakt (Var 0x14)
	- Filterwechsel erforderlich (diagnostic/problem)
- Sensors: fan level, temperatures (outdoor/extract/exhaust/supply), party current/preselect minutes, bypass temps, frost protection temp, hours on, min fan level, filter change months (diagnostic), party/zuluft/abluft levels, stage voltages (1–4, Zuluft/Abluft), nachlaufzeit seconds, software version, date/time text.

Services
- `helios_pro_ventilation.set_auto_mode` — enabled: boolean
- `helios_pro_ventilation.set_fan_level` — level: 0..4
- `helios_pro_ventilation.set_party_enabled` — enabled: boolean (write Var 0x0F; state confirmed via Var 0x10)

Entity picture (optional)
- Place `helios_ec_pro.png` either in your HA config at `www/helios_ec_pro.png` (served as `/local/helios_ec_pro.png`) or in the integration folder at `custom_components/helios_pro_ventilation/helios_ec_pro.png` (served as `/api/helios_pro_ventilation/image.png`). The Climate and Fan entities will detect and display it automatically.

## 8. Operation details

Send slots and bus pings
- Writes are only sent in a short window after a ping is seen on the bus. The integration tracks `last_ping_time` and toggles a `send_slot_active` flag; the sender thread drains the queue during this window.

Polling strategy
- Temperatures (Var 0x3A): ~every 30 seconds.
- Party current time (Var 0x10): at startup; then every 10 minutes while active, hourly otherwise.
- Bypass 2 temperature (Var 0x60): hourly (treated as integer °C).
- Hourly housekeeping: ext_contact, hours_on, party/zuluft/abluft levels, bypass1/frostschutz temps, date/time, fan stage voltages, etc.
- Startup one‑time reads: software version, min fan level, filter change months, nachlaufzeit.

Party semantics
- Enable/disable party via Var 0x0F (write‑only). The actual active state is reflected by Var 0x10 (>0 minutes remaining). The integration exposes a `set_party_enabled` service and a derived `party_enabled` binary sensor.

## 9. Diagnostic one‑shot scan

Use the switch “variablen Scan (debug)” to trigger a single pass over the variable map (HeliosVar). The integration will:
- Queue reads at ≥500 ms intervals
- Log per‑variable values at DEBUG
- Emit a single INFO summary at the end
- Write a timestamped summary to text and Markdown files in the HA config directory (listing variable code, name, values, units, notes)
- Include special handling so temperatures (Var 0x3A) and fan level (Var 0x35) appear even if not directly readable

## 10. Troubleshooting

Symptoms and checks
- No entities update: Verify the TCP bridge is reachable; check logs for missing pings. Ensure the Waveshare is in TCP Server mode and the IP/port are correct.
- Writes don’t execute: Ensure pings are seen (send slot opens); check that frames are queued; increase log level to INFO/DEBUG.
- Party sensor missing: Appears after the first Var 0x10 read; it’s polled at startup and then dynamically.
- Debug scan: See `custom_components/helios_pro_ventilation` logs; summaries are written to files with timestamps.

Logging
Add this to your Home Assistant `configuration.yaml` to control log verbosity for the integration. Use `info` for normal diagnostics or `debug` for deep protocol traces:

```yaml
logger:
  default: warning
  logs:
    custom_components.helios_pro_ventilation: info  # or "debug" for more detail
```

## 11. Known limitations and compatibility

- Verified device: Helios EC 370 pro (~2012). Other device generations may vary.
- RS‑485 wiring must be correct (A/B); RJ12 pinout variations are possible.
- The integration assumes the same frame/checksum semantics as implemented in `parser.py`.
- Some variables are read‑only or write‑only per device behavior; see `const.py` notes.

## 12. Development notes

Repository layout
- `custom_components/helios_pro_ventilation/…` — integration code
- `tests/` — parser unit tests with HA and voluptuous stubs for local runs
- `scripts/fake_helios_bridge.py` — simple TCP server you can adapt for test frames

Testing
- Run the parser tests with pytest in your dev environment.
- For HA runtime tests, place the component under `custom_components/` and reload the integration.

Contributions
- PRs are welcome for additional variables/entities, refined parsing, or improved diagnostics.

## 13. License

MIT — see `LICENSE` in the repository.


