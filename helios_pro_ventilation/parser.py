import logging, time
from typing import Dict, Any, Optional, List, Union
from .const import HeliosVar, CLIENT_ID

_LOGGER = logging.getLogger(__name__)

def _checksum(data: bytes) -> int:
    return (sum(data) + 1) & 0xFF


def _decode_sequence(payload: bytes, var: HeliosVar) -> List[Union[int, float]]:
    """Decode a sequence of values from payload using enum metadata.

    - Assumes little-endian byte order (matches current 16-bit decoding for Var_3A).
    - Applies signed handling when var.signed is True.
    - Applies var.scale to produce engineering values.
    """
    width = var.width_bits or 8
    step = max(1, width // 8)
    want = (var.count or 1) * step

    out: List[Union[int, float]] = []
    # Limit to available bytes to be defensive
    usable = min(len(payload), want)
    for i in range(0, usable, step):
        # Little-endian accumulation
        val = 0
        for b in range(step):
            if i + b >= len(payload):
                break
            val |= payload[i + b] << (8 * b)

        if var.signed and width >= 8:
            sign_bit = 1 << (width - 1)
            full = 1 << width
            if val & sign_bit:
                val -= full

        # Apply scale
        if var.scale and var.scale != 1.0:
            out.append(round(val * var.scale, 3))
        else:
            out.append(val)
    return out

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

    var = HeliosVar.Var_3A_sensors_temp
    values = _decode_sequence(payload, var)
    _LOGGER.debug("Var_3A decoded values: %s", values)
    if len(values) < 5:
        return None

    temps = {
        "temp_outdoor": values[1],
        "temp_extract": values[2],
        "temp_exhaust": values[3],
        "temp_supply":  values[4],
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
