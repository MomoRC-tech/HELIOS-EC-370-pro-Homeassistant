# Helios EC-Pro Home Assistant Integration

Custom integration for Home Assistant to control and monitor Helios EC-Pro ventilation units via a TCP bridge to the RS-485 bus.

---

## Table of Contents
1. [Overview](#1-overview)
2. [Features](#2-features)
3. [Hardware Requirements](#3-hardware-requirements)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Entities](#6-entities)
7. [Services](#7-services)
8. [Protocol basics](#8-protocol-basics)
9. [Troubleshooting](#9-troubleshooting)
10. [License](#10-license)
11. [Changelog](#11-changelog)
12. [Annex](#12-Annex)

A1. [Calendar Editor UI](#calendar-editor-ui)
A2. [Supported Hardware and wiring](#supported-hardware-and-wiring)
A3. [Debug & Protocol Details](#debug--protocol-details)

---

## 1. Overview
This integration provides local push/poll control and monitoring for Helios EC-Pro ventilation units. It communicates with the device via a TCP bridge (Waveshare/ESP32) connected to the RS-485 bus, enabling real-time updates and control from Home Assistant.

## 2. Features
- Real-time fan level, auto mode, filter warning, and temperature sensors
- Control fan level and auto mode
- Calendar-based weekly scheduling
- Device clock synchronization
- Diagnostic sensors for filter and clock status
- Lovelace dashboard support
- Debug: one‑shot scan over Helios variables with a single INFO summary + file exports
- Debug: RS‑485 stream logger switch to capture raw RX/TX frames to an HTML file with statistics (auto‑off after 15 minutes)

## 3. Hardware Requirements
- Helios EC-Pro ventilation unit
- RS-485 TCP bridge (e.g., Waveshare/ESP32)
- Home Assistant (2023.12+ recommended)

See [Supported Hardware](#supported-hardware-and-wiring) for more details and examples.

## 4. Installation
1. Download the latest release ZIP from GitHub (or clone this repository).
2. Copy the folder `helios_pro_ventilation` into your Home Assistant config's custom components folder so the final path is:  
   `config/custom_components/helios_pro_ventilation`
3. Restart Home Assistant.
4. In Home Assistant: Settings → Devices & Services → Add Integration → “Helios EC‑Pro”.

Default connection: host `192.168.0.51`, port `8234`. You can change these during the UI setup, or by a one‑time YAML import.

## 5. Configuration
Basic configuration is handled via the UI. For advanced options, see the Options dialog:
- `auto_time_sync`: Enable automatic device clock synchronization
- `time_sync_max_drift_min`: Maximum allowed drift before correction (minutes)

YAML import (optional, for initial setup):
```yaml
helios_pro_ventilation:
  host: 192.168.0.51
  port: 8234
```
After import, ongoing management is via the UI.

### Changing Host and Port After Setup
You can change the host and port after initial setup directly in the Home Assistant UI:

1. Go to Settings → Devices & Services
2. Find the "Helios EC‑Pro Ventilation" integration
3. Click on "Configure" (gear icon)
4. Update the host and/or port values
5. Click "Submit"

The integration will automatically reload with the new settings.

## 6. Entities
The integration exposes the following entities:
- **Climate**: Main control (fan level, auto/manual, presets)
- **Fan**: Direct fan speed control
- **Select**: Fan level selector
- **Sensors**:
  - Temperatures: temp_outdoor, temp_extract, temp_exhaust, temp_supply
  - Filter status
  - Device clock
  - Diagnostic info
  - fan_level (from broadcast; mirrors Var 0x35)
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
  - Datum (Gerät), Uhrzeit (Gerät), Wochentag (Gerät)
  - **Diagnostic sensors (disabled by default):**
    - Kalender Montag … Sonntag — expose raw 48-slot arrays as JSON-like text for visibility
- **Switches**:
  - Party mode
  - Calendar enable
  - Debug, one‑shot variable scan (stable id: `switch.helios_ec_pro_variablen_scan_debug`)
  - Lüftung EIN/AUS (Stufe 1): simple ON/OFF for manual level 1 vs level 0
  - RS‑485 Logger (diagnostic)
- **Binary Sensors**:
  - Filter warning
  - Clock sync status
  - Party mode
  - External contact

## 7. Services
- `set_auto_mode` (enabled: boolean)
- `set_fan_level` (level: 0–4)
- `set_party_enabled` (enabled: boolean)
- `calendar_request_day` (day: 0..6)
- `calendar_set_day` (day: 0..6, levels: exactly 48 integers 0..4)
- `calendar_copy_day` (source_day: 0..6, preset: none|weekday, all_days: bool, target_days: [0..6])
- `set_device_datetime` (year, month, day, hour, minute)
- `sync_device_time`: Sync device clock to Home Assistant host

## 8. Protocol basics (generic)

**Protocol implementation for pre-2014 Helios (variables and addresses) can be found in [`helios_pro_ventilation/const.py`](helios_pro_ventilation/const.py).**

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

## 9. Troubleshooting
- If entities don’t update, verify the bridge connection and check logs for missing pings.
- If write commands don’t take effect, ensure the bus’s ping window is being detected (send slot opens ~80 ms after ping).
- Clear `__pycache__` and reload the custom component if you’ve updated files but see old behavior.
- RS-485 HTML logs are written under your Home Assistant `/config` directory (e.g., `helios_rs485_YYYYMMDD-HHMMSS.html`).

## 10. License
MIT — see LICENSE

## 11. Changelog
See [CHANGELOG.md](CHANGELOG.md)


## 12. Annex

### Calendar Editor UI
You can view and edit the weekly schedule directly in Home Assistant:
- **Sidebar:** Look for “Helios Calendar” in the sidebar (if enabled).
- **Direct link:** Open `http://<YOUR_HOMEASSISTANT.local:8123>/api/helios_pro_ventilation/calendar.html` in your browser.

**Tip:** Add a dashboard Markdown card for one-click access:
```yaml
type: markdown
title: Helios Kalender
content: |
  [🗓️ Kalender öffnen](http://<YOUR_HOMEASSISTANT.local:8123>/api/helios_pro_ventilation/calendar.html)
```

**Editor features:**
- 7 rows (Mon..Sun), 48 half-hour slots per day
- Brush painting: pick a level (0–4), drag to paint
- Range scheduler: pick Start/End, Level, days, then click Schedule
- Overnight ranges supported (e.g., 22:00 → 06:00 wraps across midnight)
- Unsaved indicator: days with local changes show a red bullet; click Save on the row or “Save selected”
- Refresh reloads current values; missing days will be queued for reading
- Toolbar shows a compact clock/status caption (state, date/time, drift, sync) when available



## Supported Hardware and wiring

## ⚠️ Very important: safety & wiring variants

**Work only if you’re trained and understand the risks.**
**The Helios bus carries ~+24.5 V. Shorting +24.5 V to any RS-485 pin can damage the controller and/or your interface. Disconnect power before wiring and verify with a DMM.**

**Docs discrepancy (4-pin vs 6-pin): always meter first.**
Some models show RS-485 on RJ-10 (4P4C), while others (like my pre-2014 EC 370 Pro) effectively expose it on RJ-12 (6P6C). Always confirm pin polarity/roles with a meter before connecting.

**My RJ-12 (6-pin) BUS pinout to the HELIOS-BCU (EC 370 Pro, no interface box):**

*Orientation*
**Plug view: **
hold the plug with the clip down and gold contacts facing you → pins 1 → 6 left to right.

Plug (6P6C) — clip down, contacts facing you
+-------------------------------------------+
| 1   2   3   4   5   6                     |
| |   |   |   |   |   |                     |
+-------------------------------------------+

**Jack view:** 
look into the socket with the clip slot up → pins 6 → 1 left to right.

Jack (6P6C) — looking into socket, clip slot up
+-------------------------------------------+
|                     | | | | | |           |
|                     6 5 4 3 2 1           |
+-------------------------------------------+


Pin	Signal	Notes
1	+24.5 V	BUS supply (approx. 24–25 V)
2	RS485-A	A / D+
3	RS485-B	B / D–
4	(unknown)	—
5	(unknown)	—
6	GND	BUS-GND / 0 V

Quick sanity check: You should measure ~24–25 V DC between Pin 1 (+) and Pin 6 (GND) before wiring your adapter.

**Termination & topology (updated):**
RS-485 best practice is daisy-chain (“party line”) with 120 Ω at the two physical ends. However, in practice on these Helios systems, no additional termination has been required in many installs (your experience too).
Recommendation: Start with the factory/default state (no extra terminators added). Only add or enable termination if you see bus instability on long runs or in noisy environments. Use a twisted pair for A/B and share BUS-GND as reference with your adapter.

### 1. Waveshare RS485-to-Ethernet Module (Tested & Recommended)
- **Model:** Waveshare RS485 TO ETH (commonly available module)
- **Setup:**
  - Connects directly to the Helios EC‑Pro RS‑485 bus.
  - Configured in TCP Server mode.
  - Use 19200 baud, 8 data bits, no parity, 1 stop bit (8N1).
  - Default IP/Port: `192.168.0.51:8234` (can be customized).
- **Status:** Fully tested and stable. Recommended for most users seeking a reliable, plug-and-play solution.

**Example: Working Waveshare RS485-to-Ethernet Configuration**

![Waveshare RS485-to-Ethernet working configuration](https://raw.githubusercontent.com/MomoRC-tech/HELIOS-EC-370-pro-Homeassistant/main/waveshare_config_example.png)

**Key settings:**
- Device IP: `192.168.0.51`, Device Port: `8234`
- Work Mode: `TCP Server`, Baud Rate: `19200`, Databits: `8`, Stopbits: `1`, Parity: `None`
- Flow control: `None`, Protocol: `None`, No-Data-Restart: `Disable`
- Multi-host: `Yes` (default), IP mode: `Static`

This matches the defaults expected by the integration. Adjust the IP/port as needed for your network.

### 2. DIY: ESP32 with RS485 Transceiver (Advanced, Community-Supported)
- **Hardware:** ESP32 development board and RS485 transceiver module (e.g., MAX485 or similar).
- **Setup:**
  - ESP32 runs custom firmware to act as a transparent TCP server bridging RS485 and Ethernet/WiFi.
  - Bridges all data between the Helios bus and network.
  - Must match Helios requirements: 19200 baud, 8N1.
  - Exposes a TCP socket on a configurable port and IP.
- **Firmware:** Many open-source examples exist (e.g., Espressif or Arduino-based transparent serial bridge projects).
- **Status:** Experimental but functional. Allows for wireless or custom integration, suitable for advanced users.

**Notes:**
- Both solutions must operate as a transparent TCP bridge (no protocol translation, just raw RS485-to-TCP tunneling).
- The integration expects to connect to a TCP socket that directly exposes the Helios EC‑Pro RS‑485 protocol.


## Debug & Protocol Details

### Debug: One‑shot var scan
The integration includes a switch to perform a one‑time scan of all known Helios variables and log their decoded values. This is for diagnostics and development.

- Friendly name: “variablen Scan (debug)"
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

### Debug: RS‑485 stream logger
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
