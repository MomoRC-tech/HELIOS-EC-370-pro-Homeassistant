import pytest

from helios_pro_ventilation.parser import calendar_pack_levels48_to24, calendar_unpack24_to_levels48


def test_pack_unpack_all_level_3():
    levels = [3] * 48
    packed = calendar_pack_levels48_to24(levels)
    assert len(packed) == 24
    assert all(b == 0x33 for b in packed)
    unpacked = calendar_unpack24_to_levels48(packed)
    assert unpacked == levels


def test_pack_unpack_mixed_levels():
    # Hour 0: 1/4, Hour 1: 0/2
    levels = [1, 4, 0, 2] + [0, 0] * 22
    packed = calendar_pack_levels48_to24(levels)
    assert packed[0] == 0x41  # :00-29=1 (low), :30-59=4 (high)
    assert packed[1] == 0x20  # :00-29=0, :30-59=2
    unpacked = calendar_unpack24_to_levels48(packed)
    assert unpacked[:4] == [1, 4, 0, 2]


def test_pack_clamps_values():
    levels = [-1, 9] * 24  # out of range; should clamp to 0..4
    packed = calendar_pack_levels48_to24(levels)
    # low nibble 0, high nibble 4
    assert all(b == 0x40 for b in packed)
    unpacked = calendar_unpack24_to_levels48(packed)
    # high nibble was clamped to 4
    assert unpacked[0] == 0
    assert unpacked[1] == 4
