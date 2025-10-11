# Changelog

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