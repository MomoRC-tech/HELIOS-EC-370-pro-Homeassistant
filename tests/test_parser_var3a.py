import time

from helios_pro_ventilation.const import HeliosVar, CLIENT_ID
from helios_pro_ventilation.parser import try_parse_var3a


def _checksum(data: bytes) -> int:
    return (sum(data) + 1) & 0xFF


def _build_var3a_frame(words):
    # words: list of 10 signed integers (raw, before 0.1 scaling)
    payload = bytearray()
    for w in words:
        if w < 0:
            w = (1 << 16) + w
        payload.append(w & 0xFF)
        payload.append((w >> 8) & 0xFF)
    plen = 1 + len(payload)
    frame_wo_chk = bytes([CLIENT_ID, 0x00, plen, HeliosVar.Var_3A_sensors_temp]) + bytes(payload)
    return frame_wo_chk + bytes([_checksum(frame_wo_chk)])


def test_var3a_parsing_happy_path():
    # Build 10 values (scaled by 0.1 later):
    # index: 0..9 (parser uses 1..4)
    raw = [0, 123, 245, -5, 210, 0, 0, 0, 0, 0]
    frame = _build_var3a_frame(raw)
    buf = bytearray(frame)
    result = try_parse_var3a(buf)
    assert result is not None
    # values are scaled by 0.1 and rounded to 0.1 in parser
    assert result["temp_outdoor"] == 12.3
    assert result["temp_extract"] == 24.5
    assert result["temp_exhaust"] == -0.5
    assert result["temp_supply"] == 21.0
    assert "_frame_ts" in result
    assert len(buf) == 0  # frame consumed


def test_var3a_bad_checksum_is_ignored():
    raw = [0, 100, 100, 100, 100, 0, 0, 0, 0, 0]
    frame = bytearray(_build_var3a_frame(raw))
    frame[-1] ^= 0xFF  # corrupt checksum
    buf = bytearray(frame)
    # Parser should drop one byte and return None
    before = len(buf)
    result = try_parse_var3a(buf)
    assert result is None
    assert len(buf) == before - 1
