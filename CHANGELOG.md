## 5.2.5 — 2025-10-16

Patch release
- Visibility: Both Filterwechsel entities are now under Sensors on the HA device page by default.
	- filter_warning remains a PROBLEM binary sensor but is no longer categorized as diagnostic.
	- Filterwechsel (Monate) (`change_filter_months`) is now a standard number sensor (not diagnostic).
- Docs: README Entities section updated accordingly.

## 5.2.4 — 2025-10-16

Patch release
- Broadcast parsing: Extract and expose device date, time, and weekday from the periodic broadcast frame. Added a new sensor “Wochentag (Gerät)” and moved date/time to standard sensors (no longer diagnostic).
- Logger HTML: Broadcast rows now highlight known vs unknown payload bytes and include a concise summary of fan level, AUTO, filter warning, and date/time/weekday. Added explicit Ack filter and finalized summary tags to “TX ok”, “RX ok”, and “ack ok”.
- Logger stats: Footer summary now shows the trace time span, aligned columns, separate TX/RX inter-event statistics, and per-variable RX/TX frequencies. Tail bytes are flushed as “garbage” at shutdown to avoid silent drops.
- Docs: README updated to reflect broadcast-sourced date/time/weekday sensors and logger changes.

## 5.2.3 — 2025-10-16

Patch release
- Logger HTML: Added explicit Ack type (0x05) with its own color and a filter checkbox to hide/show ACK frames.
- Summary tags: Normalized wording to “TX ok” for requests and “RX ok” for responses; ACK uses “ack ok”.
- Footer summary: Added trace time span, aligned the statistics in a monospace block, and included overall TX/RX counts with min/avg/max inter-event times.
- Parser strictness: Enforced exact payload length matching for Var_07 (date=3, time=2) and Var_08 (time=2) to avoid misinterpretation.

## 5.2.2 — 2025-10-16

Patch release
- Protocol/date-time: Removed all Var_08 (time) read requests. Date/time reads now use Var_07 only; devices may reply with either date [day,month,year] or time [hour,minute] under Var_07, and both forms are handled.
- ACK handling: Generic ACK/status frames are now logged only and not interpreted as data, avoiding accidental time/date updates.
- Listener: Startup/date-time retry and hourly polling updated to queue only Var_07; drift and exception paths no longer enqueue Var_08 reads.
- Coordinator: Time writes (Var_08) remain supported, but read-backs for Var_08 are no longer queued; confirmation relies on Var_07 reads.
- Docs: Updated to reflect Var_07-only read behavior and ACK log-only policy.

## 5.2.1 — 2025-10-16

Patch release
- Send-slot gating is now address-aware and strict: a TX send slot opens only on pings from our client address (0x11). Pings from other addresses (e.g., 0x10) no longer open the slot. This reduces unintended contention when multiple devices are present on the bus.
- Parser: `try_parse_ping()` returns the ping source address for diagnostics and gating instead of a boolean.
- Listener: passes the parsed ping address to the coordinator’s `mark_ping(addr)`.
- Docs: Updated to reflect address-aware gating behavior.

## 5.0.2

Patch release
- Time sync services (set_device_datetime, sync_device_time) and options (hourly auto-sync; default 20 min drift)
- New sensors: device_clock_drift_min, device_clock_in_sync, device_date_time_state
- Faster date/time availability after startup (30s retry until present)
- Calendar UI: clock/status caption in toolbar
 - New diagnostic: RS‑485 stream logger switch to capture raw RX/TX frames to a file (auto‑off after 15 minutes); README and docs updated

## 5.1.0

Enhancements
- Time sync: new services `set_device_datetime` and `sync_device_time`; optional hourly auto-sync with drift threshold (default 20 min).
- New sensors: `device_clock_drift_min` (diagnostic), `device_clock_in_sync` (diagnostic), and `device_date_time_state` (text).
- Faster startup for date/time: retry reads every 30s until values available.
- Calendar UI: shows a compact clock/status caption (state, date/time, drift, sync) in the toolbar.
 - RS‑485 stream logger: switched to HTML output with color coding and end‑of‑file statistics (counts and min/avg/max intervals). File path now ends with `.html`.

## 5.2.0 — 2025-10-14

Enhancements
- RS‑485 stream logger UX improvements:
	- Direction arrows added in the Dir column (← RX, → TX).
	- Color legend added above the table explaining Broadcast/Known/Unknown/Garbage/Ping/TX and the garbage context key.
	- TX known/unknown frames styled with dark blue background and light blue text to distinguish outgoing frames quickly.
	- Timestamps styled (dark magenta) with added spacing for readability.
	- Consistent tag spacing after leading tokens like “ping ok”, “broadcast ok”, “request ok”, etc.
	- Garbage rows now include the previous valid frame bytes (green) before garbage bytes (red) for better context.

Docs
- README and full documentation updated to reflect HTML format details, colors, statistics, and the logger UX improvements.

Docs
- README and full docs updated for time sync services, options, sensors, and the UI caption.

# Changelog

## 5.0.1 — 2025-10-13 (proposed)
- UI: Calendar editor moved to external `calendar.html` and added a sidebar entry for quick access.
- Scheduler: Start/End time + Level + multi-day selection with a “Schedule” button.
- Option: “Clear others” toggle to reset unselected slots on selected days before applying a range.
- UX: Unsaved-change markers per day and an hours timescale header above the grid.
- Docs: README and full documentation updated with editor usage and tips.

## 5.0.0 — 2025-10-13
- Working/Stabile Release: This major release consolidates the recent calendar features and reliability fixes and marks the integration as working and stable for everyday use.
- Highlights since 4.5.x:
	- Calendar: read/write support, day copy presets, validation, and diagnostic sensors.
	- Robust parsing: calendar frames prioritized correctly; fallback startup read when no ping is observed.
	- UX: Level 1 toggle switch; unified entity image; clearer entity categories; removed misleading "level" unit labels.
	- Stability: non-blocking setup; safer service handlers; entity registration timing avoids hass=None race.
	- Tests: suite covers parser and frame builders (10 tests passing).

## 4.5.4 — 2025-10-13
- Fix: Calendar frames are now parsed by the calendar-specific decoder. The parser order was changed so calendar parsing runs before the generic var parser, and the generic parser skips calendar indices. This ensures `calendar_day_{0..6}` is populated reliably.
- Improvement: Startup calendar read fallback. If no bus ping is detected within ~15s, the integration still queues a one-time read of all 7 calendar days (Mon..Sun). Previously, this batch only triggered after the first ping.
- Stability: Entities now register with the coordinator in `async_added_to_hass`, avoiding early `async_write_ha_state()` calls when `hass` is not yet set. This removes the transient "Attribute hass is None" debug logs at startup.

## 4.5.1 — 2025-10-13
- Fix: Service handlers now guard DOMAIN data entries without a coordinator (e.g., image registration flag). This resolves an error using `calendar_request_day` where a boolean was treated as a dict ("TypeError: 'bool' object is not subscriptable").

## 4.5.2 — 2025-10-13
- Fix: Diagnostic calendar text sensors now JSON‑encode list/dict values before exposing state, so Home Assistant treats them as valid text instead of marking them unavailable. This makes “Kalender Montag … Sonntag” visible after calendar reads.

## 4.5.3 — 2025-10-13
- Fix: Avoid blocking file IO on the HA event loop by reading `manifest.json` via `hass.async_add_executor_job` during setup; removes the "Detected blocking call to open" warning.

## 4.5.0 — 2025-10-13
- Calendar:
	- New `calendar_copy_day` presets: `weekday` (Mon → Tue–Fri) and `all_days` toggle to copy to Mon–Sun.
	- Validation improvements for `calendar_set_day`: require exactly 48 integers, each in 0..4.
	- Diagnostic sensors: added seven disabled-by-default sensors (Kalender Montag … Sonntag) to expose stored 48-slot arrays for visibility.
	- Docs: README and full docs updated with examples and details.

## 4.4.1 — 2025-10-13
- Perf: Faster startup retries when the bridge isn’t reachable — 2s connect timeout and 1s backoff on connect failure; clearer logs.

## 4.4.0 — 2025-10-13
- Feature: New switch "Lüftung EIN/AUS (Stufe 1)" to toggle ventilation between OFF and manual level 1 — ideal for Android Companion entity widget.

## 4.3.0 — 2025-10-13
- UX: Removed unit label "level" from all level-type entities so Home Assistant no longer shows a unit after values.
  - Affected: fan_level, min_fan_level, party_level, zuluft_level, abluft_level, quiet_level.
  - Note: If you still see a unit in the UI, restart Home Assistant and ensure the entity has no custom unit override in the registry.
 - Feature: New switch "Lüftung EIN/AUS (Stufe 1)" to toggle ventilation between OFF and manual level 1 — ideal for Android Companion entity widget.

## 4.0.0 — 2025-10-11
- Major release: UX/docs polish and cleanups
	- Climate/Fan entity pictures standardized to the integration endpoint `/api/helios_pro_ventilation/image.png` (public; serves `config/www` image if present or falls back to packaged image/transparent PNG).
	- README now includes ready-to-copy Lovelace YAML for Climate/Fan (Picture Entity, Tile) and action buttons.
	- Duplicate binary sensor issue resolved; `filter_warning` remains as a diagnostic binary sensor and `auto_mode` is provided only via the binary_sensor platform.
	- Date/time fix finalized: Var_07/Var_08 decoding, startup reads and 10‑minute cadence are in place and tested.
	- Housekeeping: removed `TODO.md` (tracked via repository issues/notes).

## 3.2.1 — 2025-10-11
- Fix: Device date/time sensors now decode correctly and are polled at startup, with a 10-minute refresh cadence so values remain available.
- Tests: Added unit tests for generic parsing of Var_07 (date) and Var_08 (time).
- Maintenance: Minor test stubs to allow running pytest without Home Assistant installed.

## 3.2.0 — 2025-10-11
- UI: Optional device image on cards — Climate/Fan now show an image if `helios_ec_pro.png` is present either in `config/www` or packaged in the integration folder. Integration exposes `/api/helios_pro_ventilation/image.png` and falls back to a tiny transparent PNG if none found.
- UX: Improved default entity organization for better "Add to dashboard" suggestions — primary controls/sensors are prominent; diagnostic/noisy entities are categorized and many disabled by default.
- Docs: README and full docs updated with image placement instructions and entity tips.

## 3.1.2 — 2025-10-11
- Docs: Clarified that host/port YAML belongs in Home Assistant `configuration.yaml` for a one-time import; UI manages the entry afterward.
- Docs: Expanded logging instructions with `configuration.yaml` placement and `info` vs `debug` examples.

## 3.1.0 — 2025-10-11
- New entities and controls:
	- Added a native Fan entity (percentage mapped to levels 0–4; presets auto/manual).
	- Added a Select entity to directly choose Lüfterstufe [0..4].
	- New sensors: party time (current/preselect), bypass temperatures 1/2, frostschutz temp, hours on, min fan level, filter change months (diagnostic), party/zuluft/abluft levels, fan stage voltages (1–4, Zuluft/Abluft), nachlaufzeit seconds, software version, device date/time.
	- New binary sensors: Partymodus aktiv (derived from Var 0x10), Externer Kontakt.
- Protocol/polling:
	- Dynamic polling for party current time (10 min while active, hourly otherwise) and hourly polling for other slow-changing vars. Var_60 treated as °C.
- Services:
	- Added set_party_enabled service (write-only Var 0x0F) with optimistic UI + immediate Var_10 read.
- Docs:
	- README updated to list all new entities and the new Fan and Select controls.

## 3.1.1 — 2025-10-11
- Documentation: Added full project documentation (documentation.md) and linked it from README. Noted verified hardware (Helios EC 370 pro ~2012, Waveshare RS485↔Ethernet via RJ12 “Bedienteile”).

## 3.0.0 — 2025-10-11
- Major: Debug scan enhancements and documentation overhaul (tested and working)
	- Single INFO summary after scan with units and HeliosVar notes; full, unshortened values.
	- Always writes summary to timestamped .txt and .md files in HA config dir (or temp dir fallback).
	- Var_3A (temperatures) now appears in summary; Var_35 fan level synthesized from broadcast if direct read absent.
	- Stable debug switch id `switch.helios_ec_pro_variablen_scan_debug`, attached to device for integration card visibility.
	- README expanded with features, install, configuration, services, troubleshooting.
	- Tests for generic parser; all tests passing.

## 2.7.0 — 2025-10-10
- Enriched `HeliosVar` enum with structured metadata (width_bits, count, unit, scale, signed, access, note) while preserving int values.
- Parser: added `_decode_sequence()` and refactored Var_3A decoding to use metadata (centralized little-endian, signed, scaling logic).
- Sensors: derive units from enum metadata where applicable (fan level, temperatures).
- Added tests: `tests/test_parser_var3a.py` for happy path and bad checksum handling.
- Added dev harness: `scripts/fake_helios_bridge.py` TCP server emitting pings and Var_3A frames for local testing.
- Updated startup log to v2.7.0.

## 2.8.0 — 2025-10-10
- Feature: add one-shot debug scanner to read all HeliosVar-defined variables and log their decoded values.
	- New switch entity to trigger the scan once; turns off after completion.
	- Rate-limited requests (>= 500 ms between reads) via TX queue.
	- Generic parsing leverages HeliosVar metadata to decode and log values with units.
	- Implementation is minimally intrusive: new debug_scanner.py and switch.py, tiny hooks only.

## 2.8.1 — 2025-10-10
- Debug switch polish and docs/tests:
	- Renamed switch entity id to `switch.helios_ec_pro_variablen_scan_debug` and friendly name to "variablen Scan (debug)".
	- Attached switch to integration device so it appears on the integration card.
	- README: documented the switch usage and logging tips.
	- Tests: added `tests/test_parser_generic.py` for `try_parse_var_generic` happy path and bad checksum behavior.

## 2.6.1 — previous
- Minor fixes and metadata updates.