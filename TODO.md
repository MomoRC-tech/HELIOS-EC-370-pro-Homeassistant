# Project TODO

Tracked follow-ups and ideas for the Helios EC‑Pro Home Assistant integration.

## Fixes
- [done] Device date/time sensors (Datum/Uhrzeit) were unavailable — fixed generic Var 0x07/0x08 parsing, added startup reads and 10‑minute cadence; tests added.

## Entity organization
- Evaluate all entities for correct category and visibility:
  - Mark diagnostic entities (e.g., hours_on, min_fan_level, change_filter_months, voltages, nachlaufzeit) appropriately.
  - Hide noisy/secondary sensors by default where appropriate; keep primary controls prominent.
  - Review device classes and units for consistency across sensors.

## UX / Presentation
- Integrations dashboard icon cannot be customized by custom components; documented use of entity pictures instead. README updated with image endpoint details and card examples.
- [done] Add a simple dashboard view YAML that pre-adds main controls (Climate/Fan) with Picture Entity/Tile examples; included in README.

## Notes
- Date/time fix: verified scheduler reads for Var 0x07/0x08 and mapping in `broadcast_listener.py` → `coordinator.update_values` path.
- Unit tests exist for generic var parsing (Var 0x07/0x08) and Var_3A; consider adding tests for coordinator frame building and entity availability rules next.
