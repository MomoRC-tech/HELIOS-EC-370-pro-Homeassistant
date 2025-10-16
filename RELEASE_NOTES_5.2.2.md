# 5.2.2 — 2025-10-16

Patch release

- Protocol/date-time: Removed all Var_08 (time) read requests. Date/time reads now use Var_07 only. Devices may reply with date [day,month,year] and/or time [hour,minute] under Var_07; both are handled.
- ACK handling: Generic ACK/status frames are logged only and never parsed for values, preventing accidental time/date updates.
- Listener: Startup/date-time retry and hourly polling queue only Var_07. Drift checks and exception fallbacks no longer enqueue Var_08 reads.
- Coordinator: Time writes (Var_08) still supported; read-backs for Var_08 are not queued anymore. Confirmation relies on Var_07 reads.
- Documentation updated to match behavior.
