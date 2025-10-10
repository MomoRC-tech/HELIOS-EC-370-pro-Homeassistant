
from enum import IntEnum

DOMAIN = "helios_pro_ventilation"
DEFAULT_HOST = "192.168.0.51"
DEFAULT_PORT = 8234
CLIENT_ID = 0x11  # our client address on the RS-485 bus


class HeliosVar(IntEnum):
    """Helios EC-Pro variable indices according to Frank Mehnert protocol mapping."""

    Var_00_calendar_mon     = 0x00  # 24 × 8-bit
    Var_01_calendar_tue     = 0x01  # 24 × 8-bit
    Var_02_calendar_wed     = 0x02  # 24 × 8-bit
    Var_03_calendar_thu     = 0x03  # 24 × 8-bit
    Var_04_calendar_fri     = 0x04  # 24 × 8-bit
    Var_05_calendar_sat     = 0x05  # 24 × 8-bit
    Var_06_calendar_sun     = 0x06  # 24 × 8-bit (low/high half-hour)
    Var_07_date_month_year  = 0x07  # 24-bit ([0]=day, [1]=month, [2]=year)
    Var_08_time_hour_min    = 0x08  # 16-bit ([0]=hour, [1]=minutes)
    Var_0D_back_up_heating  = 0x0D  # 8-bit (0=disabled, 1=enabled)
    Var_0E_preheat_temp     = 0x0E  # 16-bit (request at offset 0x50)
    Var_0F_party_enabled    = 0x0F  # 8-bit (write-only: 0=disabled, 1=enabled)
    Var_10_party_curr_time  = 0x10  # 16-bit (minutes, current selected)
    Var_11_party_time       = 0x11  # 16-bit (minutes, pre-selected)
    Var_14_ext_contact      = 0x14  # 8-bit
    Var_15_hours_on         = 0x15  # 32-bit (hours)
    Var_16_fan_1_voltage    = 0x16  # 2 × 16-bit (Zuluft/Abluft, 0.1 V)
    Var_17_fan_2_voltage    = 0x17  # 2 × 16-bit (Zuluft/Abluft, 0.1 V)
    Var_18_fan_3_voltage    = 0x18  # 2 × 16-bit (Zuluft/Abluft, 0.1 V)
    Var_19_fan_4_voltage    = 0x19  # 2 × 16-bit (Zuluft/Abluft, 0.1 V)
    Var_1A_vacation_start   = 0x1A  # 24-bit (day, month, year)
    Var_1B_vacation_end     = 0x1B  # 24-bit (day, month, year)
    Var_1C_unknown          = 0x1C  # 16-bit 0x20 0x03 (800)
    Var_1D_unknown          = 0x1D  # 8-bit 0x3C
    Var_1E_bypass1_temp     = 0x1E  # 16-bit (0.1 °C, Außenluftbegrenzung)
    Var_1F_frostschutz      = 0x1F  # 16-bit (0.1 °C)
    Var_20_unknown          = 0x20  # 8-bit 0x01
    Var_21_weekoffs_co2     = 0x21  # 8-bit (ppm)
    Var_22_weekoffs_humdty  = 0x22  # 8-bit (%)
    Var_23_weekoffs_temp    = 0x23  # 8-bit (°C)
    Var_35_fan_level        = 0x35  # 8-bit (0..4) — READ ONLY
    Var_37_min_fan_level    = 0x37  # 8-bit (0..4)
    Var_38_change_filter    = 0x38  # 8-bit (months)
    Var_3A_sensors_temp     = 0x3A  # 10 × 16-bit (temperatures)
    Var_3B_sensors_co2      = 0x3B  # 4 × 16-bit (CO₂ sensors)
    Var_3C_sensors_humidity = 0x3C  # 4 × 16-bit (humidity sensors)
    Var_3F_unknown          = 0x3F  # 8-bit 0x00
    Var_40_unknown          = 0x40  # 8-bit 0x0A
    Var_41_unknown          = 0x41  # 8-bit 0x0A
    Var_42_party_level      = 0x42  # 8-bit (fan level)
    Var_43_unknown          = 0x43  # 8-bit 0x00
    Var_44_unknown          = 0x44  # 8-bit 0x00
    Var_45_zuluft_level     = 0x45  # 8-bit 0x02
    Var_46_abluft_level     = 0x46  # 8-bit 0x03
    Var_47_unknown          = 0x47  # 8-bit 0x00
    Var_48_software_version = 0x48  # 16-bit 0x83 0x00 (1.31)
    Var_49_nachlaufzeit     = 0x49  # 8-bit (seconds)
    Var_4A_unknown          = 0x4A  # 8-bit 0x3C
    Var_4B_unknown          = 0x4B  # 8-bit 0x3C
    Var_4C_unknown          = 0x4C  # 8-bit 0x02
    Var_4D_unknown          = 0x4D  # 8-bit 0x02
    Var_4E_vacation_enabled = 0x4E  # 8-bit (0=off, 1=on)
    Var_4F_preheat_enabled  = 0x4F  # 8-bit (0=off, 1=on)
    Var_50_preheat_temp     = 0x50  # 16-bit (0.1 °C)
    Var_51_unknown          = 0x51  # 8-bit 0x02
    Var_52_weekoffs_enabled = 0x52  # 8-bit (0=off, 1=on)
    Var_54_quiet_curr_time  = 0x54  # 16-bit (minutes, current)
    Var_55_quiet_enabled    = 0x55  # 8-bit (write-only: 0=disabled, 1=enabled)
    Var_56_quiet_time       = 0x56  # 8-bit (minutes)
    Var_57_quiet_level      = 0x57  # 8-bit (fan level)
    Var_58_unknown          = 0x58  # 26 × 8-bit 0x00 0x00 …
    Var_59_unknown          = 0x59  # 26 × 8-bit 0x01 0x00 …
    Var_5A_unknown          = 0x5A  # 26 × 8-bit 0x02 0x00 …
    Var_5B_unknown          = 0x5B  # 26 × 8-bit 0x03 0x00 …
    Var_5C_unknown          = 0x5C  # 26 × 8-bit 0x04 0x00 …
    Var_5D_unknown          = 0x5D  # 26 × 8-bit 0x05 0x00 …
    Var_5E_unknown          = 0x5E  # 26 × 8-bit 0x06 0x00 …
    Var_5F_unknown          = 0x5F  # 8-bit 0x00
    Var_60_bypass2_temp     = 0x60  # 8-bit (Bypass temperature)
    Var_61_unknown          = 0x61  # 24-bit 0x1E 0x01 0x00
    Var_62_unknown          = 0x62  # 24-bit 0x05 0x00 0x00
    Var_63_unknown          = 0x63  # 24-bit 0x0F 0x01 0x00
    Var_64_unknown          = 0x64  # 24-bit 0x05 0x04 0x06
    Var_65_unknown          = 0x65  # 16-bit 0xA5 0x00 (165)
    Var_66_unknown          = 0x66  # 16-bit 0x90 0x01 (400)
    Var_67_unknown          = 0x67  # 32-bit 0x00 0x00 0F 0F
