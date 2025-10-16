# 5.2.4 — 2025-10-16

Patch release

Highlights:
- Broadcast date/time/weekday
  - Parse device date, time, and weekday from the periodic broadcast frame
  - New text sensor: "Wochentag (Gerät)"
  - Date/Time moved from diagnostics to standard sensors
- RS‑485 logger upgrades
  - Ack (cmd=0x05) has its own category and filter; summary tags standardized to "TX ok", "RX ok", and "ack ok"
  - Broadcast rows: highlight known vs unknown payload bytes and add a compact summary (fan level, AUTO, filter warning, date/time/weekday)
  - Footer stats: trace span, aligned columns, separate TX/RX inter-event min/avg/max, per-variable RX/TX frequencies
  - Shutdown flush: any trailing bytes are logged as tail garbage to avoid silent drops
- Docs
  - README updated to reflect broadcast-sourced date/time/weekday sensors and logger behavior

No breaking changes. All tests green.
