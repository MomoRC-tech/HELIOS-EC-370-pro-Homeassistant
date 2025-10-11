# sensor.py
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from .const import DOMAIN, HeliosVar
from .coordinator import HeliosCoordinator

class HeliosBaseEntity:
    _attr_has_entity_name = True
    def __init__(self, coord: HeliosCoordinator, key: str, name: str, entry: ConfigEntry):
        self._coord = coord
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Helios EC-Pro",
            manufacturer="Helios",
            model="EC-Pro",
            configuration_url=None,
        )

    @property
    def available(self) -> bool:
        return self._key in self._coord.data and self._coord.data[self._key] is not None

class HeliosTextSensor(HeliosBaseEntity, SensorEntity):
    def __init__(self, coord, key, name, entry):
        super().__init__(coord, key, name, entry)
        self._unit = None
    @property
    def native_value(self): return self._coord.data.get(self._key)
    @property
    def native_unit_of_measurement(self): return self._unit

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord: HeliosCoordinator = data["coordinator"]

    entities = [
        HeliosNumberSensor(coord, "fan_level", "Lüfterstufe", None, entry),
        HeliosNumberSensor(coord, "temp_outdoor", "Außenlufttemperatur", "°C", entry),
        HeliosNumberSensor(coord, "temp_extract", "Ablufttemperatur", "°C", entry),
        HeliosNumberSensor(coord, "temp_exhaust", "Fortlufttemperatur", "°C", entry),
        HeliosNumberSensor(coord, "temp_supply", "Zulufttemperatur", "°C", entry),
        HeliosNumberSensor(coord, "party_curr_time_min", "Party verbleibend (min)", "min", entry),
        HeliosNumberSensor(coord, "bypass2_temp", "Bypass Temperatur 2", "°C", entry),
            HeliosNumberSensor(coord, "party_time_min_preselect", "Party Zeit (Vorauswahl)", "min", entry),
            HeliosNumberSensor(coord, "hours_on", "Betriebsstunden", "h", entry),
            HeliosNumberSensor(coord, "min_fan_level", "Minimale Lüfterstufe", None, entry),
            HeliosNumberSensor(coord, "change_filter_months", "Filterwechsel (Monate)", "months", entry),
            HeliosNumberSensor(coord, "party_level", "Party Lüfterstufe", None, entry),
            HeliosNumberSensor(coord, "zuluft_level", "Zuluft Lüfterstufe", None, entry),
            HeliosNumberSensor(coord, "abluft_level", "Abluft Lüfterstufe", None, entry),
            HeliosNumberSensor(coord, "bypass1_temp", "Bypass Temperatur 1", "°C", entry),
            HeliosNumberSensor(coord, "frostschutz_temp", "Frostschutz Temperatur", "°C", entry),
            HeliosNumberSensor(coord, "nachlaufzeit_s", "Nachlaufzeit", "s", entry),
            HeliosNumberSensor(coord, "fan1_voltage_zuluft", "Stufe 1 Spannung Zuluft", "V", entry),
            HeliosNumberSensor(coord, "fan1_voltage_abluft", "Stufe 1 Spannung Abluft", "V", entry),
            HeliosNumberSensor(coord, "fan2_voltage_zuluft", "Stufe 2 Spannung Zuluft", "V", entry),
            HeliosNumberSensor(coord, "fan2_voltage_abluft", "Stufe 2 Spannung Abluft", "V", entry),
            HeliosNumberSensor(coord, "fan3_voltage_zuluft", "Stufe 3 Spannung Zuluft", "V", entry),
            HeliosNumberSensor(coord, "fan3_voltage_abluft", "Stufe 3 Spannung Abluft", "V", entry),
            HeliosNumberSensor(coord, "fan4_voltage_zuluft", "Stufe 4 Spannung Zuluft", "V", entry),
            HeliosNumberSensor(coord, "fan4_voltage_abluft", "Stufe 4 Spannung Abluft", "V", entry),
            HeliosTextSensor(coord, "software_version", "Software Version", entry),
            HeliosTextSensor(coord, "date_str", "Datum (Gerät)", entry),
            HeliosTextSensor(coord, "time_str", "Uhrzeit (Gerät)", entry),
        HeliosBinarySensor(coord, "auto_mode", "Automatikmodus aktiv", entry),
        HeliosBinarySensor(coord, "filter_warning", "Filterwechsel erforderlich", entry),
    ]
    async_add_entities(entities)
    for e in entities:
        coord.register_entity(e)

class HeliosNumberSensor(HeliosBaseEntity, SensorEntity):
    def __init__(self, coord, key, name, unit, entry):
        super().__init__(coord, key, name, entry)
        # Prefer unit from HeliosVar when known (for keys mapping to a VAR)
        var_units_map = {
            "fan_level": HeliosVar.Var_35_fan_level.unit,
            "temp_outdoor": HeliosVar.Var_3A_sensors_temp.unit,
            "temp_extract": HeliosVar.Var_3A_sensors_temp.unit,
            "temp_exhaust": HeliosVar.Var_3A_sensors_temp.unit,
            "temp_supply": HeliosVar.Var_3A_sensors_temp.unit,
            "party_curr_time_min": HeliosVar.Var_10_party_curr_time.unit,
            "bypass2_temp": HeliosVar.Var_60_bypass2_temp.unit,
                "party_time_min_preselect": HeliosVar.Var_11_party_time.unit,
                "hours_on": HeliosVar.Var_15_hours_on.unit,
                "min_fan_level": HeliosVar.Var_37_min_fan_level.unit,
                "change_filter_months": HeliosVar.Var_38_change_filter.unit,
                "party_level": HeliosVar.Var_42_party_level.unit,
                "zuluft_level": HeliosVar.Var_45_zuluft_level.unit,
                "abluft_level": HeliosVar.Var_46_abluft_level.unit,
                "bypass1_temp": HeliosVar.Var_1E_bypass1_temp.unit,
                "frostschutz_temp": HeliosVar.Var_1F_frostschutz.unit,
                "nachlaufzeit_s": HeliosVar.Var_49_nachlaufzeit.unit,
                "fan1_voltage_zuluft": HeliosVar.Var_16_fan_1_voltage.unit,
                "fan1_voltage_abluft": HeliosVar.Var_16_fan_1_voltage.unit,
                "fan2_voltage_zuluft": HeliosVar.Var_17_fan_2_voltage.unit,
                "fan2_voltage_abluft": HeliosVar.Var_17_fan_2_voltage.unit,
                "fan3_voltage_zuluft": HeliosVar.Var_18_fan_3_voltage.unit,
                "fan3_voltage_abluft": HeliosVar.Var_18_fan_3_voltage.unit,
                "fan4_voltage_zuluft": HeliosVar.Var_19_fan_4_voltage.unit,
                "fan4_voltage_abluft": HeliosVar.Var_19_fan_4_voltage.unit,
        }
        self._unit = var_units_map.get(key, unit)
        # Mark some sensors as diagnostics
        if key == "change_filter_months":
            try:
                from homeassistant.helpers.entity import EntityCategory
                self._attr_entity_category = EntityCategory.DIAGNOSTIC
            except Exception:
                # best-effort outside HA runtime
                pass
    @property
    def native_value(self): return self._coord.data.get(self._key)
    @property
    def native_unit_of_measurement(self): return self._unit
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
class HeliosBinarySensor(HeliosBaseEntity, BinarySensorEntity):
    def __init__(self, coord, key, name, entry):
        super().__init__(coord, key, name, entry)
        # Mark "filter_warning" explicitly as a problem/diagnostic entity
        if self._key == "filter_warning":
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
    @property
    def is_on(self): 
        v = self._coord.data.get(self._key)
        return bool(v) if v is not None else False
