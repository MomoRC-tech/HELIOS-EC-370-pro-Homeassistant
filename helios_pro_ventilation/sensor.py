# sensor.py
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from .const import DOMAIN, HeliosVar
from .coordinator import HeliosCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord: HeliosCoordinator = data["coordinator"]

    entities = [
        HeliosNumberSensor(coord, "fan_level", "Lüfterstufe", None, entry),
        HeliosNumberSensor(coord, "temp_outdoor", "Außenlufttemperatur", "°C", entry),
        HeliosNumberSensor(coord, "temp_extract", "Ablufttemperatur", "°C", entry),
        HeliosNumberSensor(coord, "temp_exhaust", "Fortlufttemperatur", "°C", entry),
        HeliosNumberSensor(coord, "temp_supply", "Zulufttemperatur", "°C", entry),
        HeliosBinarySensor(coord, "auto_mode", "Automatikmodus aktiv", entry),
        HeliosBinarySensor(coord, "filter_warning", "Filterwechsel erforderlich", entry),
    ]
    async_add_entities(entities)
    for e in entities:
        coord.register_entity(e)

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
        }
        self._unit = var_units_map.get(key, unit)
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
