# 5.2.5 — 2025-10-16

Patch release

Changes:
- Sensor visibility tweaks
  - filter_warning: stays a PROBLEM-class binary sensor but is no longer diagnostic; it appears in the Sensors group on the device page.
  - Filterwechsel (Monate) (`change_filter_months`): moved from diagnostic to a standard number sensor.
- Docs: README updated to reflect these changes.

No behavior changes to parsing or control; purely UI categorization.
