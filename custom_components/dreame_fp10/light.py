"""Light platform for Dreame FP10 Air Purifier (ambient light strip)."""
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_EFFECT, ColorMode, LightEntity, LightEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .api import DreameAirPurifier
from .const import DOMAIN

EFFECT_STEADY = "Steady"
EFFECT_BREATHING = "Breathing"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DreameAmbientLight(data["coordinator"], p) for p in data["purifiers"]])

class DreameAmbientLight(CoordinatorEntity, LightEntity):
    """The FP10's single-color ambient light strip.

    Device properties (verified live): (6,6) brightness 0-100 with 0=off
    (app presets 30/50/80), (6,12) breathing effect 0/1.
    """
    _attr_has_entity_name = True
    _attr_name = "Ambient Light"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = [EFFECT_STEADY, EFFECT_BREATHING]

    def __init__(self, coordinator, purifier: DreameAirPurifier):
        super().__init__(coordinator)
        self._purifier = purifier
        self._attr_unique_id = f"{purifier.unique_id}_ambient_light"

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._purifier.unique_id)}, "name": self._purifier.name, "manufacturer": "Dreame", "model": self._purifier.model}

    @property
    def available(self): return self._purifier.available

    @property
    def is_on(self):
        return bool(self._purifier.light_brightness)

    @property
    def brightness(self):
        pct = self._purifier.light_brightness
        return None if pct is None else round(pct * 255 / 100)

    @property
    def effect(self):
        if self._purifier.light_breathing is None:
            return None
        return EFFECT_BREATHING if self._purifier.light_breathing else EFFECT_STEADY

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
        elif not self.is_on:
            pct = 80  # app's "Bright" preset
        else:
            pct = None
        if pct is not None:
            await self.hass.async_add_executor_job(self._purifier.set_light_brightness, pct)
        if ATTR_EFFECT in kwargs:
            await self.hass.async_add_executor_job(
                self._purifier.set_light_breathing, kwargs[ATTR_EFFECT] == EFFECT_BREATHING)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self._purifier.set_light_brightness, 0)
        self.async_write_ha_state()
