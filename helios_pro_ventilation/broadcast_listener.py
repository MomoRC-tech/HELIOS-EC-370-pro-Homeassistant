import socket, threading, logging, time
from .parser import (
    try_parse_broadcast,
    try_parse_var3a,
    try_parse_ping,
    try_parse_var_generic,
    try_parse_calendar,
    _checksum,
)
from .const import CLIENT_ID, HeliosVar

_LOGGER = logging.getLogger(__name__)

class HeliosBroadcastReader(threading.Thread):
    def __init__(self, host, port, coordinator, stop_event):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.coord = coordinator
        self.stop_event = stop_event
        self.buf = bytearray()
        self.sock = None
        self._sender_thread = None
        self._enqueuer_thread = None

    def run(self):
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._enqueuer_thread = threading.Thread(target=self._cyclic_enqueuer, daemon=True)
        self._sender_thread.start()
        self._enqueuer_thread.start()

        last_ping_log = 0
        while not self.stop_event.is_set():
            try:
                if not self.sock:
                    _LOGGER.info("Connecting to Helios bridge %s:%d", self.host, self.port)
                    try:
                        # Use a shorter dial timeout for snappier retries during startup
                        self.sock = socket.create_connection((self.host, self.port), timeout=2)
                        self.sock.settimeout(1)
                        _LOGGER.info("Connected to Helios bridge")
                    except Exception as ce:
                        # Connection failed quickly; brief backoff and retry without treating as a read error
                        _LOGGER.warning("Connect failed to %s:%d: %s — retrying in 1s", self.host, self.port, ce)
                        time.sleep(1)
                        continue

                chunk = self.sock.recv(256)
                if not chunk:
                    raise ConnectionError("No data received")
                self.buf.extend(chunk)
                # Tap RX bytes into optional RS-485 logger (non-intrusive)
                try:
                    logger = getattr(self.coord, "rs485_logger", None)
                    if logger is not None and hasattr(logger, "on_rx"):
                        logger.on_rx(bytes(chunk))
                except Exception:
                    pass
                made_progress = True

                while made_progress:
                    made_progress = False

                    if try_parse_ping(self.buf):
                        self.coord.mark_ping()
                        # _LOGGER.debug("Ping detected from Helios bus → send slot opened for 0.08s")
                        made_progress = True
                        continue

                    parsed = try_parse_broadcast(self.buf)
                    if parsed:
                        # _LOGGER.debug("Listener: broadcast parsed -> %s", parsed)
                        self.coord.update_values(parsed)
                        made_progress = True
                        continue

                    parsed = try_parse_var3a(self.buf)
                    if parsed:
                        self.coord.update_values(parsed)
                        # Forward a compact 0x3A result to the debug callback for scanner summaries
                        cb = getattr(self.coord, "debug_var_callback", None)
                        if callable(cb):
                            try:
                                vals = [
                                    parsed.get("temp_outdoor"),
                                    parsed.get("temp_extract"),
                                    parsed.get("temp_exhaust"),
                                    parsed.get("temp_supply"),
                                ]
                                cb({
                                    "var": HeliosVar.Var_3A_sensors_temp,
                                    "values": vals,
                                    "_frame_ts": parsed.get("_frame_ts"),
                                })
                            except Exception as _exc:
                                _LOGGER.debug("debug_var_callback (3A) failed: %s", _exc)
                        made_progress = True
                        continue

                    # Calendar day response: meta + 24 bytes
                    cal = try_parse_calendar(self.buf)
                    if cal:
                        try:
                            var = cal.get("var")
                            levels = cal.get("levels48")
                            if var is not None and isinstance(levels, list):
                                # store by day index 0..6
                                day = int(var) - int(HeliosVar.Var_00_calendar_mon)
                                self.coord.update_values({f"calendar_day_{day}": levels})
                        except Exception:
                            pass
                        made_progress = True
                        continue

                    generic = try_parse_var_generic(self.buf)
                    if generic:
                        # Forward to optional debug callback first
                        cb = getattr(self.coord, "debug_var_callback", None)
                        if callable(cb):
                            try:
                                cb(generic)
                            except Exception as _exc:
                                _LOGGER.debug("debug_var_callback failed: %s", _exc)
                        # Map a subset of vars into coordinator data for entities
                        try:
                            var = generic.get("var")
                            vals = generic.get("values") or []
                            
                            def _publish_clock_telemetry_if_ready():
                                """Compute and publish clock drift/sync immediately when both date and time are known.

                                This avoids leaving diagnostic sensors Unavailable until the hourly drift task runs.
                                """
                                try:
                                    import datetime as _dt
                                    date_s = str(self.coord.data.get("date_str") or "")
                                    time_s = str(self.coord.data.get("time_str") or "")
                                    if not date_s or not time_s:
                                        return
                                    y, mo, d = [int(x) for x in date_s.split("-")]
                                    h, mi = [int(x) for x in time_s.split(":" )]
                                    dev_dt = _dt.datetime(y, mo, d, h, mi)
                                    now_dt = _dt.datetime.now()
                                    drift = abs((now_dt - dev_dt).total_seconds()) / 60.0
                                    max_drift = max(0, int(getattr(self.coord, 'time_sync_max_drift_min', 20)))
                                    self.coord.update_values({
                                        "device_clock_drift_min": round(drift, 1),
                                        "device_clock_in_sync": drift <= max_drift,
                                        "device_date_time_state": "ok",
                                    })
                                except Exception as _exc:
                                    _LOGGER.debug("Immediate clock telemetry failed: %s", _exc)
                            if var == HeliosVar.Var_10_party_curr_time and vals:
                                # minutes remaining for current party and derived enabled flag
                                minutes = int(vals[0])
                                self.coord.update_values({
                                    "party_curr_time_min": minutes,
                                    "party_enabled": minutes > 0,
                                })
                            elif var == HeliosVar.Var_60_bypass2_temp and vals:
                                # 8-bit °C, pass through as int
                                self.coord.update_values({"bypass2_temp": int(vals[0])})
                            elif var == HeliosVar.Var_11_party_time and vals:
                                self.coord.update_values({"party_time_min_preselect": int(vals[0])})
                            elif var == HeliosVar.Var_14_ext_contact and vals:
                                self.coord.update_values({"ext_contact": int(vals[0]) != 0})
                            elif var == HeliosVar.Var_15_hours_on and vals:
                                self.coord.update_values({"hours_on": int(vals[0])})
                            elif var == HeliosVar.Var_37_min_fan_level and vals:
                                self.coord.update_values({"min_fan_level": int(vals[0])})
                            elif var == HeliosVar.Var_38_change_filter and vals:
                                self.coord.update_values({"change_filter_months": int(vals[0])})
                            elif var == HeliosVar.Var_42_party_level and vals:
                                self.coord.update_values({"party_level": int(vals[0])})
                            elif var == HeliosVar.Var_45_zuluft_level and vals:
                                self.coord.update_values({"zuluft_level": int(vals[0])})
                            elif var == HeliosVar.Var_46_abluft_level and vals:
                                self.coord.update_values({"abluft_level": int(vals[0])})
                            elif var == HeliosVar.Var_1E_bypass1_temp and vals:
                                # scaled by parser to 0.1°C already
                                self.coord.update_values({"bypass1_temp": float(vals[0])})
                            elif var == HeliosVar.Var_1F_frostschutz and vals:
                                self.coord.update_values({"frostschutz_temp": float(vals[0])})
                            elif var == HeliosVar.Var_48_software_version and vals:
                                # Expect two bytes combined into a 16-bit number by parser; if parser keeps as 1 value, derive string
                                try:
                                    ver_num = int(vals[0])
                                    major = ver_num // 100
                                    minor = ver_num % 100
                                    self.coord.update_values({"software_version": f"{major}.{minor:02d}"})
                                except Exception:
                                    # Fallback to string of values
                                    self.coord.update_values({"software_version": ".".join(str(int(v)) for v in vals)})
                            elif var == HeliosVar.Var_07_date_month_year and len(vals) >= 3:
                                day, month, year = int(vals[0]), int(vals[1]), int(vals[2])
                                self.coord.update_values({
                                    "date_str": f"{2000+year:04d}-{month:02d}-{day:02d}" if year < 100 else f"{year:04d}-{month:02d}-{day:02d}"
                                })
                                _publish_clock_telemetry_if_ready()
                            elif var == HeliosVar.Var_08_time_hour_min and len(vals) >= 1:
                                # Prefer [hour, minute] format; fall back to single value as minutes-of-day if device uses 16-bit encoding
                                hour, minute = None, None
                                try:
                                    if len(vals) >= 2:
                                        h0, m0 = int(vals[0]), int(vals[1])
                                        if 0 <= h0 <= 23 and 0 <= m0 <= 59:
                                            hour, minute = h0, m0
                                        else:
                                            # Some bridges/devices report time as 16-bit minutes-of-day split over two bytes
                                            mod = max(0, min(24 * 60 - 1, (m0 << 8) | (h0 & 0xFF)))
                                            hour, minute = mod // 60, mod % 60
                                    else:
                                        # Fallback: a single 16-bit minutes-of-day value (0..1439)
                                        mod = max(0, min(24 * 60 - 1, int(vals[0])))
                                        hour, minute = mod // 60, mod % 60
                                except Exception:
                                    pass
                                if hour is not None and minute is not None:
                                    self.coord.update_values({"time_str": f"{hour:02d}:{minute:02d}"})
                                    _publish_clock_telemetry_if_ready()
                            elif var == HeliosVar.Var_49_nachlaufzeit and vals:
                                self.coord.update_values({"nachlaufzeit_s": int(vals[0])})
                            elif var == HeliosVar.Var_16_fan_1_voltage and len(vals) >= 2:
                                self.coord.update_values({
                                    "fan1_voltage_zuluft": float(vals[0]),
                                    "fan1_voltage_abluft": float(vals[1]),
                                })
                            elif var == HeliosVar.Var_17_fan_2_voltage and len(vals) >= 2:
                                self.coord.update_values({
                                    "fan2_voltage_zuluft": float(vals[0]),
                                    "fan2_voltage_abluft": float(vals[1]),
                                })
                            elif var == HeliosVar.Var_18_fan_3_voltage and len(vals) >= 2:
                                self.coord.update_values({
                                    "fan3_voltage_zuluft": float(vals[0]),
                                    "fan3_voltage_abluft": float(vals[1]),
                                })
                            elif var == HeliosVar.Var_19_fan_4_voltage and len(vals) >= 2:
                                self.coord.update_values({
                                    "fan4_voltage_zuluft": float(vals[0]),
                                    "fan4_voltage_abluft": float(vals[1]),
                                })
                        except Exception as map_exc:
                            _LOGGER.debug("Generic var mapping failed: %s", map_exc)
                        made_progress = True
                        continue

                    if len(self.buf) > 2048:
                        self.buf.clear()

                now = time.time()
                if now - last_ping_log > 30:
                    if now - self.coord.last_ping_time > 30:
                        _LOGGER.info("No ping received from Helios bus in last 30s")
                    last_ping_log = now

                self.coord.tick()

            except (socket.timeout, BlockingIOError):
                self.coord.tick()
                continue
            except Exception as e:
                _LOGGER.warning("Read error: %s — reconnect in 3s", e)
                time.sleep(3)
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                self.sock = None

        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        _LOGGER.info("HeliosBroadcastReader stopped.")

    def _build_read_request(self, var: int) -> bytes:
        var_code = int(var)
        frame = bytes([CLIENT_ID, 0x00, 0x01, var_code])
        chksum = _checksum(frame)
        return frame + bytes([chksum])

    def _cyclic_enqueuer(self):
        last_v3a = 0.0
        last_v10 = 0.0
        last_v60 = 0.0
        # Date/time more frequent polling
        last_v07 = 0.0
        last_v08 = 0.0
        last_time_sync = 0.0
        last_dt_retry = 0.0
        # Hourly-ish vars
        last_hourly = 0.0
        # One-time at startup vars
        startup_done = False
        # One-time calendar read (all 7 days) after first ping, paced
        calendar_startup_done = False
        # Fallback timer: if no ping is observed within this window, still queue initial calendar reads
        start_time = time.time()
        calendar_fallback_seconds = 15.0
        while not self.stop_event.is_set():
            now = time.time()
            # Always poll Var_3A every ~30s for temperatures
            if now - last_v3a >= 30.0:
                frame = self._build_read_request(HeliosVar.Var_3A_sensors_temp)
                if hasattr(self.coord, 'queue_frame'):
                    self.coord.queue_frame(frame)
                last_v3a = now

            # Poll party current time (Var_10):
            # - at startup (now - 0 >= interval triggers immediately)
            # - every 10 min if party is currently enabled (derived from party_curr_time_min > 0)
            # - otherwise hourly
            party_minutes = 0
            try:
                v = self.coord.data.get("party_curr_time_min")
                if isinstance(v, (int, float)):
                    party_minutes = int(v)
            except Exception:
                party_minutes = 0
            party_interval = 600.0 if party_minutes > 0 else 3600.0
            if now - last_v10 >= party_interval:
                frame = self._build_read_request(HeliosVar.Var_10_party_curr_time)
                if hasattr(self.coord, 'queue_frame'):
                    self.coord.queue_frame(frame)
                last_v10 = now

            # Poll bypass2 temperature (Var_60) hourly
            if now - last_v60 >= 3600.0:
                frame = self._build_read_request(HeliosVar.Var_60_bypass2_temp)
                if hasattr(self.coord, 'queue_frame'):
                    self.coord.queue_frame(frame)
                last_v60 = now

            # Poll device date/time every 10 minutes to keep sensors updated
            if now - last_v07 >= 600.0:
                frame = self._build_read_request(HeliosVar.Var_07_date_month_year)
                if hasattr(self.coord, 'queue_frame'):
                    self.coord.queue_frame(frame)
                last_v07 = now
            if now - last_v08 >= 600.0:
                frame = self._build_read_request(HeliosVar.Var_08_time_hour_min)
                if hasattr(self.coord, 'queue_frame'):
                    self.coord.queue_frame(frame)
                last_v08 = now

            # Startup assist: if date/time not yet populated, retry reads every 30s until available
            try:
                if now - last_dt_retry >= 30.0:
                    date_ok = isinstance(self.coord.data.get("date_str"), str) and len(self.coord.data.get("date_str")) >= 8
                    time_ok = isinstance(self.coord.data.get("time_str"), str) and len(self.coord.data.get("time_str")) >= 4
                    if not (date_ok and time_ok):
                        self.coord.queue_frame(self._build_read_request(HeliosVar.Var_07_date_month_year))
                        self.coord.queue_frame(self._build_read_request(HeliosVar.Var_08_time_hour_min))
                        # Expose a friendly state text
                        try:
                            self.coord.update_values({"device_date_time_state": "loading"})
                        except Exception:
                            pass
                    else:
                        try:
                            self.coord.update_values({"device_date_time_state": "ok"})
                        except Exception:
                            pass
                    last_dt_retry = now
            except Exception:
                pass

            # Time sync drift check (hourly). Always compute drift; only correct when auto_time_sync is enabled.
            try:
                if now - last_time_sync >= 3600.0:
                    import datetime as _dt
                    date_s = str(self.coord.data.get("date_str") or "")
                    time_s = str(self.coord.data.get("time_str") or "")
                    if not date_s or not time_s:
                        self.coord.queue_frame(self._build_read_request(HeliosVar.Var_07_date_month_year))
                        self.coord.queue_frame(self._build_read_request(HeliosVar.Var_08_time_hour_min))
                        try:
                            self.coord.update_values({"device_date_time_state": "unknown"})
                        except Exception:
                            pass
                    else:
                        try:
                            y, mo, d = [int(x) for x in date_s.split("-")]
                            h, mi = [int(x) for x in time_s.split(":")]
                            dev_dt = _dt.datetime(y, mo, d, h, mi)
                            now_dt = _dt.datetime.now()
                            drift = abs((now_dt - dev_dt).total_seconds()) / 60.0
                            max_drift = max(0, int(getattr(self.coord, 'time_sync_max_drift_min', 20)))
                            # Publish drift and in_sync status
                            try:
                                self.coord.update_values({
                                    "device_clock_drift_min": round(drift, 1),
                                    "device_clock_in_sync": drift <= max_drift,
                                    "device_date_time_state": "ok",
                                })
                            except Exception:
                                pass
                            # Auto-correct only when enabled and drift exceeds threshold
                            if getattr(self.coord, 'auto_time_sync', False) and drift > max_drift:
                                try:
                                    if hasattr(self.coord, 'set_device_datetime'):
                                        self.coord.set_device_datetime(now_dt.year, now_dt.month, now_dt.day, now_dt.hour, now_dt.minute)
                                        _LOGGER.info("Auto time sync: corrected device clock drift %.1f min (> %d)", drift, max_drift)
                                except Exception as _exc:
                                    _LOGGER.debug("Auto time sync set failed: %s", _exc)
                        except Exception:
                            self.coord.queue_frame(self._build_read_request(HeliosVar.Var_07_date_month_year))
                            self.coord.queue_frame(self._build_read_request(HeliosVar.Var_08_time_hour_min))
                    last_time_sync = now
            except Exception as _exc:
                _LOGGER.debug("Time sync drift check failed: %s", _exc)

            # Queue one-time reads at startup for mostly-static values
            if not startup_done:
                for var in (
                    HeliosVar.Var_48_software_version,
                    HeliosVar.Var_37_min_fan_level,
                    HeliosVar.Var_38_change_filter,
                    HeliosVar.Var_49_nachlaufzeit,
                    # Also read device date/time early so sensors populate quickly
                    HeliosVar.Var_07_date_month_year,
                    HeliosVar.Var_08_time_hour_min,
                ):
                    frame = self._build_read_request(var)
                    if hasattr(self.coord, 'queue_frame'):
                        self.coord.queue_frame(frame)
                    time.sleep(0.05)
                startup_done = True

            # After first ping observed, read all 7 calendar days once, paced
            # Fallback: if no ping within calendar_fallback_seconds since thread start, queue anyway
            if (not calendar_startup_done) and (
                self.coord.last_ping_time > 0 or (now - start_time >= calendar_fallback_seconds)
            ):
                try:
                    for day in range(7):
                        var = HeliosVar(int(HeliosVar.Var_00_calendar_mon) + day)
                        frame = self._build_read_request(var)
                        if hasattr(self.coord, 'queue_frame'):
                            self.coord.queue_frame(frame)
                        # Pace calendar requests slightly higher to be gentle
                        time.sleep(0.1)
                    calendar_startup_done = True
                    if self.coord.last_ping_time > 0:
                        _LOGGER.info("Queued initial calendar read for all days (Mon..Sun) after first ping")
                    else:
                        _LOGGER.info(
                            "Queued initial calendar read for all days (Mon..Sun) via fallback (no ping observed in %.0fs)",
                            calendar_fallback_seconds,
                        )
                except Exception as _exc:
                    _LOGGER.debug("Calendar startup read queue failed: %s", _exc)

            # Hourly polling for slowly changing vars
            if now - last_hourly >= 3600.0:
                for var in (
                    HeliosVar.Var_14_ext_contact,
                    HeliosVar.Var_15_hours_on,
                    HeliosVar.Var_11_party_time,
                    HeliosVar.Var_42_party_level,
                    HeliosVar.Var_45_zuluft_level,
                    HeliosVar.Var_46_abluft_level,
                    HeliosVar.Var_1E_bypass1_temp,
                    HeliosVar.Var_1F_frostschutz,
                    HeliosVar.Var_07_date_month_year,
                    HeliosVar.Var_08_time_hour_min,
                    HeliosVar.Var_16_fan_1_voltage,
                    HeliosVar.Var_17_fan_2_voltage,
                    HeliosVar.Var_18_fan_3_voltage,
                    HeliosVar.Var_19_fan_4_voltage,
                ):
                    frame = self._build_read_request(var)
                    if hasattr(self.coord, 'queue_frame'):
                        self.coord.queue_frame(frame)
                    time.sleep(0.05)
                last_hourly = now

            # Pace the loop fairly fine but light
            for _ in range(10):
                if self.stop_event.is_set():
                    break
                time.sleep(0.5)

    def _sender_loop(self):
        while not self.stop_event.is_set():
            self.coord.send_slot_event.wait(timeout=0.5)
            if self.stop_event.is_set():
                break
            if not self.coord.send_slot_active and self.coord.last_ping_time == 0:
                self.coord.send_slot_active = True
            if not (self.sock and getattr(self.coord, 'tx_queue', None)):
                continue
            if self.coord.tx_queue:
                frame = self.coord.tx_queue.popleft()
                try:
                    self.sock.sendall(frame)
                    # Tap TX bytes into optional RS-485 logger
                    try:
                        logger = getattr(self.coord, "rs485_logger", None)
                        if logger is not None and hasattr(logger, "on_tx"):
                            logger.on_tx(bytes(frame))
                    except Exception:
                        pass
                    var_idx = frame[3] if len(frame) >= 5 else None
                    if var_idx == HeliosVar.Var_3A_sensors_temp:
                        _LOGGER.debug("Sent Var_3A sensor read request: %s", frame.hex(' '))
                    else:
                        _LOGGER.debug("Sent frame: %s", frame.hex(' '))
                except Exception as e:
                    _LOGGER.warning("Send failed: %s", e)
            while self.coord.send_slot_active and not self.stop_event.is_set():
                time.sleep(0.005)
