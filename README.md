# Helios EC‑Pro custom integration for Home Assistant

This custom component integrates Helios EC‑Pro ventilation units over a TCP bridge into Home Assistant. It exposes sensors and fan/climate control and writes commands during brief "send slot" windows.

Note: This project is verified to work with a HELIOS EC 370 pro ventilation system (circa 2012). The RS‑485 interface is provided by a Waveshare RS485‑to‑Ethernet module connected directly to the Helios RS‑485 (19200 baud, 8N1).

Full documentation: see `helios_pro_ventilation/documentation.md`.

---

## Table of Contents

- [Features](#features)
- [Supported Hardware](#supported-hardware)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Debug: One-shot var scan](#debug-one-shot-var-scan)
 - [Debug: RS-485 stream logger](#debug-rs-485-stream-logger)
- [Protocol basics (generic)](#protocol-basics-generic)
- [Services](#services)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)
- [Changelog](#changelog)
- [Lovelace examples: Climate and Fan](#lovelace-examples-climate-and-fan)
 - [Calendar editor UI](#calendar-editor-ui)
- [Roadmap / TODO](#roadmap--todo)

---

## Features
- Fan control (auto/manual, levels 0–4)
- Temperature sensors (outdoor, extract, exhaust, supply)
- Filter warning as a diagnostic binary sensor
- Debug: one‑shot scan over Helios variables with a single INFO summary + file exports
- Debug: RS‑485 stream logger switch to capture raw RX/TX frames to an HTML file with color coding and end‑of‑file statistics (auto‑off after 15 minutes)
 - Weekly calendar read/write services with packing of 48 half-hour levels per day
 - Copy-day service to duplicate schedules (Mon → Tue–Fri or all days)
 - Embedded calendar editor UI (sidebar + direct URL) with range scheduler
 - Optional device time sync: manual services and opt-in hourly auto sync with drift threshold

---



## Supported Hardware

This integration has been verified to work with the following hardware setups for bridging Home Assistant to the Helios EC‑Pro RS‑485 bus:

### 1. Waveshare RS485-to-Ethernet Module (Tested & Recommended)

- **Model:** Waveshare RS485 TO ETH (commonly available module)
- **Setup:**  
  - Connects directly to the Helios EC‑Pro RS‑485 bus.
  - Configured in TCP Server mode.
  - Use 19200 baud, 8 data bits, no parity, 1 stop bit (8N1).
  - Default IP/Port: `192.168.0.51:8234` (can be customized).
- **Status:**  
  - **Fully tested and stable.**
  - Recommended for most users seeking a reliable, plug-and-play solution.

#### Example: Working Waveshare RS485-to-Ethernet Configuration

Below is a screenshot of a known-good configuration for the Waveshare RS485-to-Ethernet module, as used with this integration:

![Waveshare RS485-to-Ethernet working configuration](https://raw.githubusercontent.com/MomoRC-tech/HELIOS-EC-370-pro-Homeassistant/main/waveshare_config_example.png)

**Key settings:**
- Device IP: `192.168.0.51`, Device Port: `8234`
- Work Mode: `TCP Server`, Baud Rate: `19200`, Databits: `8`, Stopbits: `1`, Parity: `None`
- Flow control: `None`, Protocol: `None`, No-Data-Restart: `Disable`
- Multi-host: `Yes` (default), IP mode: `Static`

This matches the defaults expected by the integration. Adjust the IP/port as needed for your network.

### 2. DIY: ESP32 with RS485 Transceiver (Advanced, Community-Supported)

- **Hardware:**  
  - ESP32 development board.
  - RS485 transceiver module (e.g., MAX485 or similar).
- **Setup:**  
  - ESP32 runs custom firmware to act as a transparent TCP server bridging RS485 and Ethernet/WiFi.
  - Bridges all data between the Helios bus and network.
  - Must match Helios requirements: 19200 baud, 8N1.
  - Exposes a TCP socket on a configurable port and IP.
- **Firmware:**  
  - Many open-source examples exist (e.g., Espressif or Arduino-based transparent serial bridge projects).
  - Community support and DIY documentation may vary.
- **Status:**  
  - **Experimental but functional.**
  - Allows for wireless or custom integration, suitable for advanced users.

### Notes

- **Both solutions must operate as a transparent TCP bridge** (no protocol translation, just raw RS485-to-TCP tunneling).
- The integration expects to connect to a TCP socket that directly exposes the Helios EC‑Pro RS‑485 protocol.

---

## Installation

Manual install (short and complete):

- Download the latest release ZIP from GitHub (or clone this repository).
- Copy the folder `helios_pro_ventilation` into your Home Assistant config's custom components folder so the final path is:  
  `config/custom_components/helios_pro_ventilation`
- Restart Home Assistant.
- In Home Assistant: Settings → Devices & Services → Add Integration → “Helios EC‑Pro”.

Default connection: host `192.168.0.51`, port `8234`. You can change these during the UI setup, or by a one‑time YAML import.

---

## Configuration

The integration supports import from YAML for initial setup. Put this in your Home Assistant `configuration.yaml` and restart once to import defaults:

```yaml
helios_pro_ventilation:
  host: 192.168.0.51
  port: 8234
```

It then creates a config entry in the UI for ongoing management.

### Changing Host and Port After Setup

You can change the host and port after initial setup directly in the Home Assistant UI:

1. Go to Settings → Devices & Services
2. Find the "Helios EC‑Pro Ventilation" integration
3. Click on "Configure" (gear icon)
4. Update the host and/or port values
5. Click "Submit"

The integration will automatically reload with the new settings.

---

## Entities

- Climate (fan control)
- Fan (percentage control 0–100 mapped to levels 0–4; presets auto/manual)
- Select: Lüfterstufe (Auswahl) — options [0..4] mapped to fan levels
- Binary sensors:
  - filter warning
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
  - Filterwechsel (Monate) (Var 0x38)
  - Party/Zuluft/Abluft Lüfterstufen (Var 0x42/0x45/0x46)
  - Stufe 1–4 Spannungen Zuluft/Abluft (Var 0x16..0x19)
  - Nachlaufzeit (Sekunden) (Var 0x49)
  - Software Version (Var 0x48)
  - Datum (Gerät), Uhrzeit (Gerät), Wochentag (Gerät) — parsed from the periodic broadcast frame
- Switches:
  - Debug, one‑shot variable scan (stable id: `switch.helios_ec_pro_variablen_scan_debug`)
  - Lüftung EIN/AUS (Stufe 1): simple ON/OFF for manual level 1 vs level 0 (for widgets)
  - RS‑485 Logger (diagnostic): captures raw RS‑485 RX/TX traffic to a timestamped file; turns off automatically after 15 minutes

- Diagnostic sensors (disabled by default):
  - Kalender Montag … Sonntag — expose raw 48-slot arrays as JSON-like text for visibility

---

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

---

## Debug: RS‑485 stream logger

The integration includes a diagnostic switch to capture the raw RS‑485 byte stream (both RX and TX) to a file without affecting normal operation.

- Entity: “RS‑485 Logger” (diagnostic; disabled by default in the registry)
- How it works:
  - When turned on, all incoming and outgoing bytes are tapped and fed to a parallel parser.
  - The parser detects and marks:
    - Valid generic frames ([addr, cmd, plen, var, payload, chk])
    - Broadcast frames (0xFF 0xFF …)
    - Pings (4‑byte sync)
    - Acknowledge/status frames (cmd=0x05) — filterable as their own type
    - Any unmatched bytes as “garbage”
  - Known variable IDs are resolved using the HeliosVar map and values are decoded using the same metadata (width/scale), appended as labels like “ID 0x16 (Var_16_fan_1_voltage) values=[…]”.
- Auto‑off: If left on, the switch automatically turns off after 15 minutes.
- Log location and format:
  - A timestamped HTML file is created in your HA config directory, e.g. `<config>/helios_rs485_YYYYMMDD-HHMMSS.html`.
  - Open it in a browser to see a color‑coded table:
    - Broadcast and known frames are shown in green tones
    - Unknown frames and garbage are shown in red tones
    - Pings are shown in gray
    - There are quick filters (including Ack) to focus on specific categories.
  - The file ends with a "Summary" section with aligned columns showing:
    - Trace span (first → last event time)
    - Counts and min/avg/max inter‑event intervals for TX frames and RX frames (separately)
    - Counts/intervals for pings and broadcasts; Ack/known/unknown totals; total garbage bytes
    - Per‑variable RX/TX frequency list for generic frames
  - Broadcast rows highlight known vs unknown payload bytes and include a compact summary with fan level, AUTO, filter warning, and the device date/time/weekday parsed from the broadcast.
  - On shutdown, any residual trailing bytes are flushed as tail garbage so nothing is silently dropped.
  - Tip: You can also open the file as plain text if needed.

Notes:
- Row summary tags use TX ok / RX ok for successful requests/responses and ack ok for acknowledgements.

Note: This logger is passive and has minimal overhead. When the switch is off, there is no impact on the integration.

---

## Protocol basics (generic)

This integration talks the simple Helios EC‑Pro RS‑485 protocol. A quick reference:

- Checksum
  - For all frames, the last byte is a checksum: chk = (sum(all previous bytes) + 1) & 0xFF.

- Generic variable frames (read/write)
  - Layout: [addr, cmd, plen, var, payload..., chk]
    - addr: our client address (0x11 by default)
    - cmd: 0x00 = read, 0x01 = write
    - plen: number of bytes that follow (var + payload)
    - var: variable index (see HeliosVar in const.py)
    - payload: optional data bytes (for write or response)
  - Read request (no payload): [0x11, 0x00, 0x01, var, chk]
  - Write request (N data bytes): [0x11, 0x01, 1+N, var, data×N, chk]
  - Responses from the device use the same header shape and checksum.
  - Multi‑byte values are little‑endian; signed/scale come from the variable metadata. Example: Var_3A temperatures are 10 × 16‑bit signed with scale 0.1 °C.

- Broadcast frames
  - Layout: [0xFF, 0xFF, plen, payload..., chk]
  - Carry current fan level, auto flag, filter warning, as well as device date/time and weekday; emitted periodically by the bus. This integration uses the broadcast frame as the primary source for these sensors.

- Bus ping
  - 4‑byte pattern: [b0, 0x00, 0x00, chk]
  - A short “send slot” (~80 ms) opens after a ping; this integration queues writes to send during that window.

Example (read Var_3A):
- Request: [0x11, 0x00, 0x01, 0x3A, chk]
- The checksum is computed from the first 4 bytes: chk = (0x11 + 0x00 + 0x01 + 0x3A + 1) & 0xFF.

---

## Services
- `set_auto_mode` (enabled: boolean)
- `set_fan_level` (level: 0–4)
- `set_party_enabled` (enabled: boolean)
- `calendar_request_day` (day: 0..6)
- `calendar_set_day` (day: 0..6, levels: exactly 48 integers 0..4)
  - Tip: Enter the levels as a JSON array in the UI (object selector), e.g. `[0,1,1,2,...]`.
- `calendar_copy_day` (source_day: 0..6, preset: none|weekday, all_days: bool, target_days: [0..6])
  - If `preset=weekday`, copies to Tue–Fri; if `all_days=true`, copies to Mon–Sun and ignores `target_days`.
  - If the source calendar isn’t loaded yet, the integration queues a read and skips copying (try again afterward).
- `set_device_datetime` (year, month, day, hour, minute) — writes the device’s internal date/time.
 - `sync_device_time` — sets the device clock to the Home Assistant host’s current local time.

Options (Configure → Options)
- `auto_time_sync` (bool): when enabled, the integration checks the device time hourly and corrects it if drift exceeds the threshold.
- `time_sync_max_drift_min` (int, default 2): maximum permitted drift in minutes before auto-correction.

Sensor
- Diagnostic sensor `device_clock_drift_min` (disabled by default): shows current drift (minutes) between device clock and HA host time.
 - Diagnostic binary sensor `device_clock_in_sync` (disabled by default): true if drift <= threshold.
 - Text sensor `Geräteuhr Status` indicates "unknown/loading/ok".

Date/time protocol notes
- Sensors: Device date, time, and weekday are parsed from the periodic broadcast frame and exposed as standard sensors.
- Reads: The integration performs Var 0x07 reads for clock sync/drift logic; Var 0x08 reads are not issued.
- Writes: Time writes to Var 0x08 are supported; confirmation relies on subsequent Var 0x07 reads or later broadcast updates.
- ACK/status frames are logged and marked as such (filterable in the HTML logger) and are not interpreted as values.

---

## Troubleshooting
- If entities don’t update, verify the bridge connection and check logs for missing pings.
- If write commands don’t take effect, ensure the bus’s ping window is being detected (send slot opens ~80 ms after ping).
- Clear `__pycache__` and reload the custom component if you’ve updated files but see old behavior.
 - Where to find the RS‑485 HTML log (HA OS): Files are written under your Home Assistant `/config` directory. Use the File Editor add‑on or Samba share to open `helios_rs485_YYYYMMDD-HHMMSS.html` directly in a browser.

---

## Development
- Code is threaded for IO; entity state updates are pushed via the Home Assistant loop.
- Tests included for frame parsing; run with `pytest`.
- A fake TCP bridge is provided in `scripts/fake_helios_bridge.py` for local testing.

---

## Filter maintenance tips

The integration exposes two filter-related entities:

- Filterwechsel (Monate): Number of months until the next filter change (from Var 0x38). This is a slow-changing value.
- Filterwechsel erforderlich (binary): Turns on when the unit requests a filter change.

Example notification automation (send a message when the warning turns on):

```yaml
alias: Helios Filterwechsel Hinweis
description: Benachrichtigung, wenn Filterwechsel erforderlich ist
trigger:
  - platform: state
    entity_id: binary_sensor.helios_filterwechsel_erforderlich
    to: 'on'
action:
  - service: notify.mobile_app_mein_telefon
    data:
      title: Helios EC-Pro
      message: Filterwechsel erforderlich.
mode: single
```

You can also create a dashboard card that shows both the months remaining and the warning state.

---

## License
MIT — see LICENSE

---

## Changelog
See CHANGELOG.md

---

## Lovelace examples: Climate and Fan

Below are minimal, ready-to-copy examples showing the picture in standard cards and exposing common controls. Replace the entity ids with the ones from your system (for example `climate.helios_luftung`).

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

---


## Calendar editor UI — quick access

You can view and edit the weekly schedule directly in Home Assistant:

- **Sidebar:** Look for “Helios Calendar” in the sidebar (if enabled).
- **Direct link:** Open `/api/helios_pro_ventilation/calendar.html` in your browser (bookmark it for convenience).

**Tip:** Add a dashboard Markdown card for one-click access:

```yaml
type: markdown
title: Helios Kalender
content: |
  [🗓️ Kalender öffnen](/api/helios_pro_ventilation/calendar.html)
```

---

**Editor features:**
- 7 rows (Mon..Sun), 48 half-hour slots per day
- Brush painting: pick a level (0–4), drag to paint
- Range scheduler: pick Start/End, Level, days, then click Schedule
  - “Clear others” resets unselected slots to 0 before applying
  - Overnight ranges supported (e.g., 22:00 → 06:00 wraps across midnight)
- Unsaved indicator: days with local changes show a red bullet; click Save on the row or “Save selected”
- Refresh reloads current values; missing days will be queued for reading
- Toolbar shows a compact clock/status caption (state, date/time, drift, sync) when available

---

## Roadmap / TODO
See TODO.md for planned fixes and improvements.
