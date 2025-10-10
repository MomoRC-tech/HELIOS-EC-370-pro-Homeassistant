import logging, time
from typing import Dict, Any, Optional
from .const import HeliosVar, CLIENT_ID

_LOGGER = logging.getLogger(__name__)

def _checksum(data: bytes) -> int:
    return (sum(data) + 1) & 0xFF

def try_parse_broadcast(buf: bytearray) -> Optional[Dict[str, Any]]:
    if len(buf) < 27 or not (buf[0] == 0xFF and buf[1] == 0xFF):
        return None
    plen = buf[2]
    total = 3 + plen + 1
    if len(buf) < total:
        return None
    frame = bytes(buf[:total])
    calc = _checksum(frame[:-1])
    if frame[-1] != calc:
        buf.pop(0)
        return None
    del buf[:total]
    return {
        "fan_level": frame[9],
        "auto_mode": bool(frame[10] & 0x01),
        "filter_warning": bool(frame[13] & 0x01),
        "_frame_ts": time.time(),
    }

def try_parse_var3a(buf: bytearray) -> Optional[Dict[str, Any]]:
    if len(buf) < 5:
        return None
    addr, cmd, plen = buf[0], buf[1], buf[2]
    total = 3 + plen + 1
    if len(buf) < total:
        return None
    frame = bytes(buf[:total])
    if frame[3] != HeliosVar.Var_3A_sensors_temp:
        return None
    calc = _checksum(frame[:-1])
    if frame[-1] != calc:
        buf.pop(0)
        return None
    del buf[:total]
    payload = frame[4:-1]
    _LOGGER.debug("Var_3A raw payload: %s", payload.hex(" "))

    words = []
    for i in range(0, min(len(payload), 20), 2):
        if i + 1 >= len(payload):
            break
        w = payload[i] | (payload[i + 1] << 8)
        if w & 0x8000:
            w -= 0x10000
        words.append(w)
    _LOGGER.debug("Var_3A decoded words: %s", words)
    if len(words) < 5:
        return None

    temps = {
        "temp_outdoor": words[1] * 0.1,
        "temp_extract": words[2] * 0.1,
        "temp_exhaust": words[3] * 0.1,
        "temp_supply":  words[4] * 0.1,
    }

    values = {}
    for key, t in temps.items():
        if t >= 200 or t <= -40:
            _LOGGER.info("HeliosPro: %s sensor invalid or missing (%.1f °C)", key, t)
            values[key] = None
        else:
            values[key] = round(t, 1)
    values["_frame_ts"] = time.time()

    _LOGGER.debug(
        "HeliosPro: Var_3A parsed → outdoor=%s °C, extract=%s °C, exhaust=%s °C, supply=%s °C",
        values["temp_outdoor"], values["temp_extract"],
        values["temp_exhaust"], values["temp_supply"],
    )
    return values

def try_parse_ping(buf: bytearray) -> bool:
    if len(buf) < 4:
        return False
    b0, b1, b2, b3 = buf[0], buf[1], buf[2], buf[3]
    chk = (b0 + b1 + b2 + 1) & 0xFF
    if b1 == 0x00 and b2 == 0x00 and b3 == chk:
        del buf[:4]
        return True
    return False
