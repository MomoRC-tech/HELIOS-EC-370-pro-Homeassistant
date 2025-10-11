import socket, threading, logging, time
from .parser import try_parse_broadcast, try_parse_var3a, try_parse_ping, try_parse_var_generic, _checksum
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
                    self.sock = socket.create_connection((self.host, self.port), timeout=5)
                    self.sock.settimeout(1)
                    _LOGGER.info("Connected to Helios bridge")

                chunk = self.sock.recv(256)
                if not chunk:
                    raise ConnectionError("No data received")
                self.buf.extend(chunk)
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
                                self.coord.update_values({"date_str": f"{2000+year:04d}-{month:02d}-{day:02d}" if year < 100 else f"{year:04d}-{month:02d}-{day:02d}"})
                            elif var == HeliosVar.Var_08_time_hour_min and len(vals) >= 2:
                                hour, minute = int(vals[0]), int(vals[1])
                                self.coord.update_values({"time_str": f"{hour:02d}:{minute:02d}"})
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
                _LOGGER.warning("Read error: %s", e)
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
        # Hourly-ish vars
        last_hourly = 0.0
        # One-time at startup vars
        startup_done = False
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
                    var_idx = frame[3] if len(frame) >= 5 else None
                    if var_idx == HeliosVar.Var_3A_sensors_temp:
                        _LOGGER.debug("Sent Var_3A sensor read request: %s", frame.hex(' '))
                    else:
                        _LOGGER.debug("Sent frame: %s", frame.hex(' '))
                except Exception as e:
                    _LOGGER.warning("Send failed: %s", e)
            while self.coord.send_slot_active and not self.stop_event.is_set():
                time.sleep(0.005)
