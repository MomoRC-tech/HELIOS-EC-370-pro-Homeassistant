# Release v5.2.0 — 2025-10-14

This release refines the RS‑485 HTML logger and updates docs. No protocol or API changes.

## Highlights
- Direction arrows in Dir column (← RX, → TX)
- Color legend above the table (Broadcast/Known/Unknown/Garbage/Ping/TX)
- TX known/unknown frames in dark blue with light blue text
- Timestamps in dark magenta with extra spacing
- Consistent tag spacing after tokens like "ping ok", "broadcast ok", etc.
- Garbage rows now include the previous valid frame bytes (green) before garbage bytes (red)
- End-of-file statistics retained (counts and min/avg/max inter-arrival intervals)

## Files changed
- `helios_pro_ventilation/debug/rs485_logger.py` — HTML styling and UX improvements
- `README.md` — logger docs and troubleshooting tip updated
- `helios_pro_ventilation/documentation.md` — logger documentation updates
- `CHANGELOG.md` — 5.2.0 entry added
- `helios_pro_ventilation/manifest.json` — version bumped to 5.2.0

## How to upgrade
- Copy the updated `custom_components/helios_pro_ventilation` folder into your HA `/config/custom_components/`.
- Restart Home Assistant.

## Verification
- HTML log renders correctly with legend, arrows, and colors.
- No blocking I/O on the Home Assistant event loop from the logger.
- Existing entities and services unaffected.
