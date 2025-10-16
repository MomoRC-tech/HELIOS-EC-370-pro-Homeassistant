# 5.2.3 — 2025-10-16

Patch release

- Logger HTML UX:
  - New Ack frame type (0x05) with dedicated color and filter toggle.
  - Summary tags standardized: “TX ok” (request), “RX ok” (response), “ack ok” (acknowledge), “frame ok” (generic).
  - Footer stats now show the trace time span and aligned, readable metrics, including overall TX/RX counts and min/avg/max inter-event intervals.
- Parser/date-time:
  - Stricter matching for Var_07 (exactly 3 for date, 2 for time) and Var_08 (2 for time).
- Tests: suite updated implicitly by behavior; all tests pass (12).
