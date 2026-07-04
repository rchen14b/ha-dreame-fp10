"""Select platform for Dreame FP10 Air Purifier."""
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .api import DreameAirPurifier, MODE_NAME_TO_VALUE
from .const import DOMAIN, PRESET_MODES

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DreameModeSelect(data["coordinator"], p) for p in data["purifiers"]])

class DreameModeSelect(CoordinatorEntity, SelectEntity):
    """Direct mode control: Smart / Sleep / Customize / Pet (mirrors the fan's preset mode)."""
    _attr_has_entity_name = True
    _attr_name = "Mode"
    _attr_icon = "mdi:tune-variant"
    _attr_options = PRESET_MODES

    def __init__(self, coordinator, purifier: DreameAirPurifier):
        super().__init__(coordinator)
        self._purifier = purifier
        self._attr_unique_id = f"{purifier.unique_id}_mode"

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._purifier.unique_id)}, "name": self._purifier.name, "manufacturer": "Dreame", "model": self._purifier.model}

    @property
    def available(self): return self._purifier.available

    @property
    def current_option(self):
        mode = self._purifier.mode
        return mode if mode in PRESET_MODES else None

    async def async_select_option(self, option: str) -> None:
        mode_value = MODE_NAME_TO_VALUE.get(option)
        if mode_value is not None:
            await self.hass.async_add_executor_job(self._purifier.set_mode, mode_value)
            self.async_write_ha_state()
