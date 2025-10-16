# 5.2.1 — 2025-10-16

Patch release

- Send-slot gating is now address-aware and strict: a TX send slot opens only on pings from our client address (0x11). Pings from other addresses (e.g., 0x10) no longer open the slot.
- Parser: `try_parse_ping()` returns the ping source address for diagnostics and gating.
- Listener: passes the parsed ping address to the coordinator’s `mark_ping(addr)`.
- Docs updated to reflect the behavior.

Notes
- Initial startup behavior is unchanged: if no ping has ever been seen, the sender still allows an initial send to get going; thereafter, only 0x11 pings open slots.
- If you need different gating, we can add an option to configure allowed ping addresses.
