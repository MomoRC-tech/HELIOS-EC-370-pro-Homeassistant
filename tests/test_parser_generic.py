import time

from helios_pro_ventilation.const import HeliosVar, CLIENT_ID
from helios_pro_ventilation.parser import try_parse_var_generic


def _checksum(data: bytes) -> int:
    return (sum(data) + 1) & 0xFF


def _build_generic_frame(var: HeliosVar, payload: bytes) -> bytes:
    # Frame: [addr, cmd, plen, var, payload..., chk]
    plen = 1 + len(payload)
    head = bytes([CLIENT_ID, 0x00, plen, int(var)])
    chk = _checksum(head + payload)
    return head + payload + bytes([chk])


def test_generic_parsing_var48_scalar():
    # Var_48_software_version is 16-bit in the mapping; craft a simple scalar
    var = HeliosVar.Var_48_software_version
    # Example value 0x0083 (just a placeholder), little-endian
    payload = bytes([0x83, 0x00])
    frame = _build_generic_frame(var, payload)
    buf = bytearray(frame)

    result = try_parse_var_generic(buf)
    assert result is not None
    assert result["var"] == var
    assert result["values"] == [0x0083]
    assert "_frame_ts" in result
    assert len(buf) == 0  # frame consumed


def test_generic_bad_checksum_drops_byte():
    var = HeliosVar.Var_48_software_version
    payload = bytes([0x83, 0x00])
    frame = bytearray(_build_generic_frame(var, payload))
    frame[-1] ^= 0xFF

    buf = bytearray(frame)
    before = len(buf)
    result = try_parse_var_generic(buf)
    assert result is None
    assert len(buf) == before - 1


def test_generic_parsing_date_time_bytes():
    # Var_07 should now decode three 8-bit bytes: day, month, year (0..99)
    day, month, year = 11, 10, 25  # 2025-10-11
    var = HeliosVar.Var_07_date_month_year
    payload = bytes([day, month, year])
    frame = _build_generic_frame(var, payload)
    buf = bytearray(frame)
    res = try_parse_var_generic(buf)
    assert res is not None
    assert res["var"] == var
    assert res["values"] == [day, month, year]
    assert len(buf) == 0

    # Var_08 should decode two 8-bit bytes: hour, minute
    hour, minute = 7, 5
    var = HeliosVar.Var_08_time_hour_min
    payload = bytes([hour, minute])
    frame = _build_generic_frame(var, payload)
    buf = bytearray(frame)
    res = try_parse_var_generic(buf)
    assert res is not None
    assert res["var"] == var
    assert res["values"] == [hour, minute]
    assert len(buf) == 0
