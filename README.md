# Helios EC-Pro Home Assistant Integration

Custom integration for Home Assistant to control and monitor Helios EC-Pro ventilation units via a TCP bridge to the RS-485 bus.

---

## Table of Contents
1. [Overview](#overview)
2. [Features](#features)
3. [Hardware Requirements](#hardware-requirements)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Entities](#entities)
7. [Services](#services)
8. [Troubleshooting](#troubleshooting)
9. [License](#license)
10. [Changelog](#changelog)
11. [Calendar Editor UI](#calendar-editor-ui)

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

## 3. Hardware Requirements
- Helios EC-Pro ventilation unit
- RS-485 TCP bridge (e.g., Waveshare/ESP32)
- Home Assistant (2023.12+ recommended)

See [Supported Hardware](#supported-hardware) for detailed setup instructions and examples.

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

## 6. Entities
The integration exposes the following entities:
- **Climate**: Main control (fan level, auto/manual, presets)
- **Fan**: Direct fan speed control
- **Select**: Fan level selector
- **Sensors**: Temperatures, filter status, device clock, diagnostic info
- **Switches**: Party mode, calendar enable, debug/RS-485 logger
- **Binary Sensors**: Filter warning, clock sync status, party mode, external contact

## 7. Services
- `set_auto_mode` (enabled: boolean)
- `set_fan_level` (level: 0–4)
- `set_party_enabled` (enabled: boolean)
- `calendar_request_day` (day: 0..6)
- `calendar_set_day` (day: 0..6, levels: exactly 48 integers 0..4)
- `calendar_copy_day` (source_day: 0..6, preset: none|weekday, all_days: bool, target_days: [0..6])
- `set_device_datetime` (year, month, day, hour, minute)
- `sync_device_time`: Sync device clock to Home Assistant host

## 8. Troubleshooting
- If entities don’t update, verify the bridge connection and check logs for missing pings.
- If write commands don’t take effect, ensure the bus’s ping window is being detected (send slot opens ~80 ms after ping).
- Clear `__pycache__` and reload the custom component if you’ve updated files but see old behavior.
- RS-485 HTML logs are written under your Home Assistant `/config` directory (e.g., `helios_rs485_YYYYMMDD-HHMMSS.html`).

## 9. License
MIT — see LICENSE

## 10. Changelog
See [CHANGELOG.md](CHANGELOG.md)

## 11. Calendar Editor UI
You can view and edit the weekly schedule directly in Home Assistant:
- **Sidebar:** Look for “Helios Calendar” in the sidebar (if enabled).
- **Direct link:** Open `/api/helios_pro_ventilation/calendar.html` in your browser.

**Tip:** Add a dashboard Markdown card for one-click access:
```yaml
type: markdown
title: Helios Kalender
content: |
  [🗓️ Kalender öffnen](/api/helios_pro_ventilation/calendar.html)
```

**Editor features:**
- 7 rows (Mon..Sun), 48 half-hour slots per day
- Brush painting: pick a level (0–4), drag to paint
- Range scheduler: pick Start/End, Level, days, then click Schedule
- Overnight ranges supported (e.g., 22:00 → 06:00 wraps across midnight)
- Unsaved indicator: days with local changes show a red bullet; click Save on the row or “Save selected”
- Refresh reloads current values; missing days will be queued for reading
- Toolbar shows a compact clock/status caption (state, date/time, drift, sync) when available

## Supported Hardware

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
