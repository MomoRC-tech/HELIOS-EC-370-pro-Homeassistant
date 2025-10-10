# Changelog

## 2.7.0 — 2025-10-10
- Enriched `HeliosVar` enum with structured metadata (width_bits, count, unit, scale, signed, access, note) while preserving int values.
- Parser: added `_decode_sequence()` and refactored Var_3A decoding to use metadata (centralized little-endian, signed, scaling logic).
- Sensors: derive units from enum metadata where applicable (fan level, temperatures).
- Added tests: `tests/test_parser_var3a.py` for happy path and bad checksum handling.
- Added dev harness: `scripts/fake_helios_bridge.py` TCP server emitting pings and Var_3A frames for local testing.
- Updated startup log to v2.7.0.

## 2.6.1 — previous
- Minor fixes and metadata updates.