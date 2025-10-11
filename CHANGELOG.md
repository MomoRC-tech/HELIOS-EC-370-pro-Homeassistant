# Changelog

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