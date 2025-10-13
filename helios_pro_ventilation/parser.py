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


def calendar_pack_levels48_to24(levels48: List[int]) -> bytes:
    """Pack 48 half-hour levels (0..4) into 24 hourly bytes (nibbles).

    For each hour h: low nibble -> :00–:29, high nibble -> :30–:59.
    """
    if len(levels48) != 48:
        raise ValueError("levels48 must have length 48")
    out = bytearray(24)
    for h in range(24):
        l0 = max(0, min(4, int(levels48[2 * h])))
        l1 = max(0, min(4, int(levels48[2 * h + 1])))
        out[h] = ((l1 & 0x0F) << 4) | (l0 & 0x0F)
    return bytes(out)


def calendar_unpack24_to_levels48(bytes24: bytes) -> List[int]:
    """Unpack 24 hourly bytes (nibbles) into 48 half-hour levels (0..4)."""
    if len(bytes24) != 24:
        raise ValueError("bytes24 must have length 24")
    levels: List[int] = [0] * 48
    for h in range(24):
        b = bytes24[h]
        l0 = b & 0x0F
        l1 = (b >> 4) & 0x0F
        levels[2 * h] = l0 if 0 <= l0 <= 4 else 0
        levels[2 * h + 1] = l1 if 0 <= l1 <= 4 else 0
    return levels


def try_parse_calendar(buf: bytearray) -> Optional[Dict[str, Any]]:
    """Parse calendar response frames with 3 meta bytes + 24 hourly bytes.

    Frame: [0x11, 0x01, 0x1C, var(0x00..0x06), META0, META1, META2, 24 data bytes, chk]
    Returns: {"var": HeliosVar, "meta": [m0,m1,m2], "bytes24": bytes, "levels48": list}
    """
    if len(buf) < 5:
        return None
    addr, cmd, plen = buf[0], buf[1], buf[2]
    total = 3 + plen + 1
    if len(buf) < total:
        return None
    frame = bytes(buf[:total])
    if not (addr == 0x11 and cmd == 0x01 and plen >= 0x1C):
        return None
    var_idx = frame[3]
    if var_idx < int(HeliosVar.Var_00_calendar_mon) or var_idx > int(HeliosVar.Var_06_calendar_sun):
        return None
    calc = _checksum(frame[:-1])
    if frame[-1] != calc:
        buf.pop(0)
        return None
    del buf[:total]
    try:
        var = HeliosVar(var_idx)
    except Exception:
        return None
    # Payload after var contains 3 meta bytes then 24 data bytes
    payload = frame[4:-1]
    if len(payload) < 27:
        # not enough bytes for meta+24 data
        return None
    meta = [payload[0], payload[1], payload[2]]
    data24 = bytes(payload[3:3 + 24])
    levels = calendar_unpack24_to_levels48(data24)
    return {"var": var, "meta": meta, "bytes24": data24, "levels48": levels, "_frame_ts": time.time()}

def try_parse_var_generic(buf: bytearray) -> Optional[Dict[str, Any]]:
    """Try to parse a generic var response [addr, cmd, plen, var_idx, data..., chk].

    Uses HeliosVar metadata to decode the payload. Returns a dict with keys:
    {"var": HeliosVar, "values": list, "_frame_ts": float}
    """
    if len(buf) < 5:
        return None
    addr, cmd, plen = buf[0], buf[1], buf[2]
    total = 3 + plen + 1
    if len(buf) < total:
        return None
    frame = bytes(buf[:total])
    var_idx = frame[3]
    try:
        var = HeliosVar(var_idx)
    except Exception:
        return None
    calc = _checksum(frame[:-1])
    if frame[-1] != calc:
        buf.pop(0)
        return None
    del buf[:total]
    payload = frame[4:-1]
    values = _decode_sequence(payload, var)
    return {"var": var, "values": values, "_frame_ts": time.time()}
