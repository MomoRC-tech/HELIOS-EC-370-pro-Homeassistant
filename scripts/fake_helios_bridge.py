import socket
import threading
import time
from typing import Tuple


HOST = "0.0.0.0"
PORT = 8234


def _checksum(data: bytes) -> int:
    return (sum(data) + 1) & 0xFF


def build_ping() -> bytes:
    # 4-byte ping: b0, 0x00, 0x00, chk(b0+1)
    b0 = 0x55
    chk = (b0 + 0x00 + 0x00 + 1) & 0xFF
    return bytes([b0, 0x00, 0x00, chk])


def build_var3a_frame(outdoor=120, extract=230, exhaust=-5, supply=210) -> bytes:
    # raw 16-bit LE words; scale 0.1 in client
    words = [0, outdoor, extract, exhaust, supply, 0, 0, 0, 0, 0]
    payload = bytearray()
    for w in words:
        if w < 0:
            w = (1 << 16) + w
        payload.append(w & 0xFF)
        payload.append((w >> 8) & 0xFF)
    # frame: [addr=0x11, cmd=0x00, plen=1+len(payload), var=0x3A, payload..., chk]
    addr = 0x11
    var = 0x3A
    body = bytes([addr, 0x00, 1 + len(payload), var]) + bytes(payload)
    return body + bytes([_checksum(body)])


def client_thread(conn: socket.socket, addr: Tuple[str, int]):
    conn.settimeout(1.0)
    try:
        next_sensor = 0.0
        while True:
            # Send a ping every 250ms
            conn.sendall(build_ping())
            # Sensor frame every 2s
            t = time.time()
            if t >= next_sensor:
                conn.sendall(build_var3a_frame())
                next_sensor = t + 2.0
            time.sleep(0.25)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    print(f"Fake Helios bridge listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(1)
        while True:
            conn, a = s.accept()
            print(f"Client connected: {a}")
            threading.Thread(target=client_thread, args=(conn, a), daemon=True).start()


if __name__ == "__main__":
    main()
