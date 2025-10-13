import pytest

from helios_pro_ventilation.const import HeliosVar, CLIENT_ID
from helios_pro_ventilation.coordinator import HeliosCoordinatorWithQueue
from helios_pro_ventilation.parser import calendar_pack_levels48_to24


class DummyHass:
    class Loop:
        def call_soon_threadsafe(self, *args, **kwargs):
            pass
    def __init__(self):
        self.loop = self.Loop()

def test_build_calendar_write_extended_bytes():
    hass = DummyHass()
    coord = HeliosCoordinatorWithQueue(hass)
    # Pattern: 0,1,2,3,4 repeating across 48 slots
    levels = [i % 5 for i in range(48)]
    # Use Monday var
    var = HeliosVar.Var_00_calendar_mon
    frame = coord._build_calendar_write_extended(var, levels)

    # Expected layout:
    # [CLIENT_ID, 0x01, 0x34, var, 0x00, 0x00, 24 packed, 25x 0x00, chk]
    assert frame[0] == CLIENT_ID
    assert frame[1] == 0x01
    assert frame[2] == 0x34
    assert frame[3] == int(var)
    assert frame[4] == 0x00 and frame[5] == 0x00

    packed = calendar_pack_levels48_to24(levels)
    assert frame[6:6+24] == bytes(packed)
    # Padding 25 zeros
    assert frame[6+24:6+24+25] == bytes([0x00] * 25)

    # Check checksum
    chk = (sum(frame[:-1]) + 1) & 0xFF
    assert frame[-1] == chk


def test_read_request_bytes():
    hass = DummyHass()
    coord = HeliosCoordinatorWithQueue(hass)
    frame = coord._build_read_request(HeliosVar.Var_02_calendar_wed)
    assert frame[:3] == bytes([CLIENT_ID, 0x00, 0x01])
    assert frame[3] == int(HeliosVar.Var_02_calendar_wed)
    chk = (sum(frame[:-1]) + 1) & 0xFF
    assert frame[-1] == chk
