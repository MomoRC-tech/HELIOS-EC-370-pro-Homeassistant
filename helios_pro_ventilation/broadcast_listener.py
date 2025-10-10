import socket, threading, logging, time
from .parser import try_parse_broadcast, try_parse_var3a, try_parse_ping, _checksum
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
        frame = bytes([CLIENT_ID, 0x00, 0x01, var])
        chksum = _checksum(frame)
        return frame + bytes([chksum])

    def _cyclic_enqueuer(self):
        while not self.stop_event.is_set():
            frame = self._build_read_request(HeliosVar.Var_3A_sensors_temp)
            if hasattr(self.coord, 'queue_frame'):
                self.coord.queue_frame(frame)
            time.sleep(30)

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
