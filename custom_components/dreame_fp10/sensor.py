"""Sensor platform for Dreame FP10 Air Purifier."""
import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .api import DreameAirPurifier, PROP_FILTER2_LIFE, PROP_FILTER3_LIFE
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for p in data["purifiers"]:
        entities.extend([DreamePM25Sensor(data["coordinator"], p), DreameAirQualitySensor(data["coordinator"], p),
                         DreameFilterLifeSensor(data["coordinator"], p), DreameFilterDaysLeftSensor(data["coordinator"], p),
                         DreameFilterUsedSensor(data["coordinator"], p), DreameDeviceLocationSensor(data["coordinator"], p)])
        # Extra FP10 filter components (live: 99% / 89%) — added only if the device reports them
        if p.has_prop(PROP_FILTER2_LIFE["siid"], PROP_FILTER2_LIFE["piid"]):
            entities.append(DreameFilter2LifeSensor(data["coordinator"], p))
        if p.has_prop(PROP_FILTER3_LIFE["siid"], PROP_FILTER3_LIFE["piid"]):
            entities.append(DreameFilter3LifeSensor(data["coordinator"], p))
    async_add_entities(entities)

class DreameBaseSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, purifier: DreameAirPurifier, key: str, name: str):
        super().__init__(coordinator)
        self._purifier = purifier
        self._attr_unique_id = f"{purifier.unique_id}_{key}"
        self._attr_name = name
    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._purifier.unique_id)}, "name": self._purifier.name, "manufacturer": "Dreame", "model": self._purifier.model}
    @property
    def available(self): return self._purifier.available

class DreamePM25Sensor(DreameBaseSensor):
    _attr_device_class = SensorDeviceClass.PM25
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    _attr_icon = "mdi:molecule"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "pm25", "PM2.5")
    @property
    def native_value(self): return self._purifier.pm25

class DreameAirQualitySensor(DreameBaseSensor):
    _attr_icon = "mdi:air-filter"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "air_quality", "Air Quality Level")
    @property
    def native_value(self): return self._purifier.air_quality_level

class DreameFilter2LifeSensor(DreameBaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:air-filter"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "filter2_life", "Filter 2 Life")
    @property
    def native_value(self): return self._purifier.filter2_life

class DreameFilter3LifeSensor(DreameBaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:air-filter"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "filter3_life", "Filter 3 Life")
    @property
    def native_value(self): return self._purifier.filter3_life

class DreameFilterLifeSensor(DreameBaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:air-filter"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "filter_life", "HEPA Filter Life")
    @property
    def native_value(self): return self._purifier.filter_life

class DreameFilterDaysLeftSensor(DreameBaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:calendar-clock"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "filter_days_left", "HEPA Filter Days Left")
    @property
    def native_value(self): return self._purifier.filter_days_left

class DreameFilterUsedSensor(DreameBaseSensor):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_icon = "mdi:clock-outline"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "filter_used", "HEPA Filter Hours Used")
    @property
    def native_value(self): return self._purifier.filter_hours_used

class DreameDeviceLocationSensor(DreameBaseSensor):
    _attr_icon = "mdi:map-marker"
    def __init__(self, coordinator, purifier): super().__init__(coordinator, purifier, "device_location", "Device Location")
    @property
    def native_value(self): return self._purifier.device_location
