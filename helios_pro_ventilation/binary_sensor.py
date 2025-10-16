from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN
from .coordinator import HeliosCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
	data = hass.data[DOMAIN][entry.entry_id]
	coord: HeliosCoordinator = data["coordinator"]

	entities = [
		HeliosBinarySensor(coord, "auto_mode", "Automatikmodus aktiv", entry),
		HeliosBinarySensor(coord, "filter_warning", "Filterwechsel erforderlich", entry),
		HeliosBinarySensor(coord, "party_enabled", "Partymodus aktiv", entry),
		HeliosBinarySensor(coord, "ext_contact", "Externer Kontakt", entry),
		HeliosBinarySensor(coord, "device_clock_in_sync", "Geräteuhr synchron", entry),
	]
	async_add_entities(entities)


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


class HeliosBinarySensor(HeliosBaseEntity, BinarySensorEntity):
	def __init__(self, coord, key, name, entry):
		super().__init__(coord, key, name, entry)
		# Mark "filter_warning" explicitly as a problem binary sensor (non-diagnostic)
		if self._key == "filter_warning":
			self._attr_device_class = BinarySensorDeviceClass.PROBLEM
		# Hide ext_contact by default; it's an auxiliary input
		if self._key == "ext_contact":
			try:
				self._attr_entity_category = EntityCategory.DIAGNOSTIC
				self._attr_entity_registry_enabled_default = False
			except Exception:
				pass
		# Mark device_clock_in_sync as diagnostic and hidden by default
		if self._key == "device_clock_in_sync":
			try:
				self._attr_entity_category = EntityCategory.DIAGNOSTIC
				self._attr_entity_registry_enabled_default = False
			except Exception:
				pass

	@property
	def is_on(self):
		v = self._coord.data.get(self._key)
		return bool(v) if v is not None else False

	async def async_added_to_hass(self):
		try:
			if hasattr(self._coord, "register_entity"):
				self._coord.register_entity(self)
		except Exception:
			pass
