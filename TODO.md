# Project TODO

Tracked follow-ups and ideas for the Helios EC‑Pro Home Assistant integration.

## Fixes
- Device date/time sensors (Datum/Uhrzeit) show as unavailable — investigate why `date_str` / `time_str` remain None and ensure they’re polled/parsed correctly (generic Var 0x07/0x08 mapping path).

## Entity organization
- Evaluate all entities for correct category and visibility:
  - Mark diagnostic entities (e.g., hours_on, min_fan_level, change_filter_months, voltages, nachlaufzeit) appropriately.
  - Hide noisy/secondary sensors by default where appropriate; keep primary controls prominent.
  - Review device classes and units for consistency across sensors.

## UX / Presentation
- Add a picture for the integration (device icon on the integration card); include asset under `helios_pro_ventilation/` and wire via `device_info` or manifest imagery if applicable.
- Add a simple dashboard view YAML that pre-adds the main controls (Climate, Fan, Fan level Select, key sensors). Provide as example in docs.

## Notes
- When addressing the date/time fix, verify scheduler reads for Var 0x07/0x08 and mapping in `broadcast_listener.py` → `coordinator.update_values` path.
- Consider adding unit tests for generic var parsing (Var 0x07/0x08/0x48) and for entity availability rules.
