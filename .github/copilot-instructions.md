These notes help an AI coding agent be productive working on the Helios EC‑Pro Home Assistant custom integration.

High level
- This repository is a Home Assistant custom integration providing a "local_push" integration to read and control Helios EC‑Pro ventilation units over a TCP bridge to the device's RS‑485 bus. The integration lives in the `helios_pro_ventilation/` package.
- Key responsibilities:
  - `__init__.py`: integration setup, config entry import, service registration, lifecycle (start/stop reader threads) and wiring of coordinator/reader into `hass.data`.
  - `broadcast_listener.py`: long-running network listener + sender threads. Reads raw frames from a TCP socket, parses them and updates the coordinator. Also enqueues periodic read requests and drains coordinator TX queue.
  - `parser.py`: frame parsing helpers (broadcast frames, Var_3A sensor frames, ping frames) and simple checksum logic.
  - `coordinator.py`: central in-memory state, entity registration, TX queue builders (write frames), and helper methods used by services and entities.
  - `sensor.py` and `climate.py`: Home Assistant entities that expose coordinator data and call coordinator methods to change device state (fan level / auto mode).

What to know about architecture and data flow
- The integration uses a push/poll hybrid: `HeliosBroadcastReader` receives broadcast frames pushed by the Helios bridge and updates `HeliosCoordinator.data` via `update_values()`. The coordinator notifies registered entities by calling their `async_write_ha_state()` on the Home Assistant loop.
- Outgoing writes use a short "send slot" window opened when a ping is observed on the bus. The reader's `_sender_loop` waits for `coord.send_slot_event` and then sends frames dequeued from `coord.tx_queue`. `HeliosCoordinatorWithQueue.queue_frame()` is the producer for outgoing frames.
- Sensor parsing: `try_parse_broadcast()` extracts fan level, auto mode and filter warning. `try_parse_var3a()` decodes 16-bit temperature words (see `const.HeliosVar.Var_3A_sensors_temp`) and maps them to `temp_outdoor`, `temp_extract`, `temp_exhaust`, `temp_supply`.

Important files to reference (examples and patterns)
- `__init__.py` — config flow import, creating `HeliosCoordinatorWithQueue`, starting `HeliosBroadcastReader`, storing `hass.data[DOMAIN][entry_id] = {"coordinator", "reader", "stop_event"}` and registering services (`set_auto_mode`, `set_fan_level`). Use this file to understand entity wiring and lifecycle.
- `coordinator.py` — `update_values()` merges new values and triggers entity updates. `set_auto_mode()` and `set_fan_level()` build frames and call `queue_frame()`; created frames use `CLIENT_ID` and a simple checksum function.
- `broadcast_listener.py` — the main network loop. When modifying networking behavior, replicate the current threading model: one thread for reader (this class), internal sender thread (`_sender_loop`) and a cyclic enqueuer (`_cyclic_enqueuer`) that periodically requests Var_3A.
- `parser.py` — contains the exact checksum used and the frame layout assumptions. If you change frame boundaries or checksum, update both `parser.py` and `coordinator._checksum` consistently.
- `const.py` — authoritative mapping of variables and default host/port. Use `HeliosVar` enum values when building or interpreting frames.

Project-specific conventions and patterns
- Push model: Entities don't poll; they rely on the coordinator to call `async_write_ha_state()` from the HA loop. Use `hass.loop.call_soon_threadsafe(...)` from background threads as `coordinator.update_values()` already does.
- Threading + HA loop: Background IO runs in threads. Avoid synchronous blocking calls on the HA main thread. When signalling HA state changes from threads, call `hass.loop.call_soon_threadsafe(...)` or use thread-safe events.
- Send slot behavior: Outgoing frames must be transmitted within an 80 ms window after a ping; the code represents this as `send_slot_active` and `send_slot_expires`. If adding new write frames, use `queue_frame()` and rely on the existing sender logic.
- Services registration: `__init__.py` registers two integration services and binds `services.yaml` to show the service descriptions in the UI. When adding services, update both the `async_register` call and `services.yaml`.

Developer workflows (how to run and debug)
- This is a Home Assistant custom component. Typical dev flow:
  1. Put this folder under Home Assistant's `custom_components/helios_pro_ventilation`.
  2. Restart Home Assistant (or reload integrations) to pick up changes.
  3. Use Home Assistant logs to troubleshoot (`logger` uses `logging.getLogger(__name__)`). Increase log level for the integration in `configuration.yaml` during development:

```yaml
logger:
  default: warning
  logs:
    custom_components.helios_pro_ventilation: debug
```

- Local network testing: the integration connects to a TCP bridge (default host `192.168.0.51`, port `8234`). If you don't have a device, you can run a small TCP server that streams test frames to emulate the bridge. Use the `parser.py` helpers to craft valid frames (checksum = (sum(data)+1)&0xFF).

Quick troubleshooting tips
- If entities never become available, check `coord.data` keys (populated keys include `fan_level`, `auto_mode`, `filter_warning`, `temp_*`). Entities mark themselves available only when the key exists and is not None.
- If writes don't reach the device, verify ping detection: `try_parse_ping()` removes the 4-byte ping sequence and sets `coord.last_ping_time`; absent pings mean the sender won't get send slots.
- Keep `HeliosVar.Var_3A_sensors_temp` requests unchanged: the reader enqueues a Var_3A read every 30s in `_cyclic_enqueuer`.

When editing code, prefer small, testable changes
- Unit tests: none shipped. When adding tests, target `parser.py` frame parsing and `coordinator` frame building. Use concrete byte arrays from `parser` debug output as fixtures.
- Avoid changing threading model unless necessary. If you must, update `__init__.py` lifecycle (start/stop threads and `stop_event`) and ensure `async_unload_entry()` sets `stop_event` so threads exit cleanly.

If you need more context
- Ask for the exact Home Assistant version used for runtime compatibility checks (entity/base class APIs vary across versions).
- I can generate example frames, small unit tests for `parser.py`, or a TCP bridge test harness on request.

Please review and tell me which areas should be expanded (tests, example frames, or run/debug scripts).
