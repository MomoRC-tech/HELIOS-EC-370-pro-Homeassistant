# Helios EC-Pro 270/370 Home Assistant Integration

Custom integration for Home Assistant to control and monitor Helios EC-Pro 270/370 (pre 2014)ventilation units via a TCP bridge to the RS-485 bus.

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
This integration provides local push/poll control and monitoring for Helios EC-Pro ventilation units. It communicates with the device via a TCP bridge (Waveshare/ESP32) connected to the RS-485 bus.

## 2. Features
 - Real-time fan level, auto mode, filter warning, and temperature sensors
 - Control fan level and auto mode
 - Calendar-based weekly scheduling
 - Device clock synchronization
 - Diagnostic sensors for filter and clock status
 - Lovelace dashboard support
 - Debug: one‑shot scan over Helios variables with a single INFO summary + file exports
 - Debug: RS‑485 stream logger switch to capture raw RX/TX frames to an HTML file with statistics (auto‑off after 15 minutes)
 - Icing protection: If the outdoor temperature (temp_outdoor) stays below the configurable frost protection threshold (sensor.helios_ec_pro_frostschutz_temperatur) for more than 10 minutes, the fan level is forced to 0 to reduce icing risk.
 - Switch entity "Eisüberwachung enable" allows toggling the icing protection feature (enabled by default).
 - Binary sensor "Eisschutz status" indicates when icing protection is active.
 - Counter sensor "Eisschutz Auslösungen (24h)" shows how many times icing protection was triggered in the last 24 hours (rolling window; updates automatically).
 - Service `reset_icing_trigger_counter` to manually reset the rolling counter.
 - Long‑term statistics compatible icing trigger counter (state_class=measurement)

## 3. Hardware Requirements
- Helios EC-Pro 270/370 (pre 2014) ventilation unit
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
- Climate: Main control (fan level, auto/manual, presets)
- Fan: Direct fan speed control
- Select: Fan level selector
- Sensors:
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
  - Eisschutz Auslösungen (24h) (rolling icing trigger count, measurement)
  - Diagnostic sensors (disabled by default): Kalender Montag … Sonntag
- Switches:
  - Party mode
  - Calendar enable
  - Debug, one‑shot variable scan
  - Lüftung EIN/AUS (Stufe 1)
  - RS‑485 Logger
  - Eisüberwachung enable (icing protection toggle)
- Binary Sensors:
  - Filter warning
  - Clock sync status
  - Party mode
  - External contact
  - Eisschutz status (icing protection active)

## 7. Services
| Service | Description | Params |
|---------|-------------|--------|
| `helios_pro_ventilation.set_auto_mode` | Enable/disable AUTO mode | enabled: bool |
| `helios_pro_ventilation.set_fan_level` | Set manual fan level | level: 0..4 |
| `helios_pro_ventilation.set_party_enabled` | Enable/disable Party mode | enabled: bool |
| `helios_pro_ventilation.calendar_request_day` | Request calendar for day | day: 0..6 |
| `helios_pro_ventilation.calendar_set_day` | Write calendar day (48 slots) | day: 0..6, levels: [48x 0..4] |
| `helios_pro_ventilation.calendar_copy_day` | Copy calendar day to targets | source_day, preset, all_days, target_days |
| `helios_pro_ventilation.set_device_datetime` | Set device date/time | year, month, day, hour, minute |
| `helios_pro_ventilation.sync_device_time` | Sync device clock to HA time | (none) |
| `helios_pro_ventilation.reset_icing_trigger_counter` | Reset icing 24h trigger counter | (none) |

## 8. Protocol basics (generic)
(unchanged)

## 9. Troubleshooting
(unchanged)

## 10. License
MIT — see LICENSE

## 11. Changelog
See CHANGELOG.md

## 12. Annex
(unchanged)
