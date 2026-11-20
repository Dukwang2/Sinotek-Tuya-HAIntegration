"""Human-readable charger telemetry."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_platform
from homeassistant.util import slugify

from .entity import ChargerEntity
from .profile import readings

# Use reading names from profile.py. Hidden sensors still provide states for
# templates and automations; users can change visibility in Home Assistant.
HIDDEN_READINGS = {
    "Session Cost",  # DP 102 (x_metrics`c`): Cost of current session
    "Schedule Savings",  # DP 102 (x_metrics`s`): Savings from schedule
    "RCD Type",  # DP 106 (x_charger_info`r`): RCD type (0 = None, 1 = Type A, 2 = Type B)
    "Diagnostic Work State",  # DP 109 (`x_work_st_debug): Diagnostic work state
    "Market",  # DP 114 (x_us_eu): US / EU
    "Customer Contact",  # DP 116 (x_contact): Customer contact number
    "Firmware Debug",  # DP 153 (x_lang_cfg): Firmware debug info
    "Legacy NFC Setting",  # DP 155 (x_nfc_cfg): Legacy NFC setting
    "Product Capabilities",  # DP 157 (x_product_variant): Product capabilities
    "Temperature Mode (reserved)",  # DP 161 (x_temp_mode): Temperature mode
    "Currency", # DP 165 (x_unit): Currency
}


async def async_setup_entry(hass, entry, async_add_entities):
    for coordinator in entry.runtime_data:
        def add(entities, subentry=coordinator.subentry):
            async_add_entities(entities, config_subentry_id=subentry.subentry_id if subentry else None)
        setup_charger(hass, entry, coordinator, add)


def setup_charger(hass, entry, coordinator, async_add_entities):
    platform = entity_platform.async_get_current_platform()
    known = set()

    @callback
    def add_readings():
        new = []
        for name, (_, unit, cls) in readings(coordinator.data).items():
            if name not in known:
                new.append(ChargerSensor(coordinator, name, unit, cls))
                known.add(name)
        if new:
            async_add_entities(new)

    entry.async_on_unload(coordinator.async_add_listener(add_readings, context=platform.domain))
    add_readings()


class ChargerSensor(ChargerEntity, SensorEntity):
    """One typed reading from the charger payload."""

    def __init__(self, coordinator, name, unit, cls):
        super().__init__(coordinator, slugify(name), name)
        self._reading = name
        self._attr_entity_registry_enabled_default = name not in HIDDEN_READINGS
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = cls

    @property
    def native_value(self):
        return readings(self.coordinator.data).get(self._reading, (None,))[0]
