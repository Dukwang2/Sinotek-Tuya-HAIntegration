"""Continuous charging-current control for DP 150."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.exceptions import HomeAssistantError

from .entity import ChargerEntity
from .profile import charging_current_limit


async def async_setup_entry(hass, entry, async_add_entities):
    for coordinator in entry.runtime_data:
        async_add_entities(
            [ChargingCurrent(coordinator, "150", "Charging Current")],
            config_subentry_id=coordinator.subentry.subentry_id if coordinator.subentry else None,
        )


class ChargingCurrent(ChargerEntity, NumberEntity):
    """Set amperage in 1 A steps within the charger's limits."""

    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 6
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    @property
    def native_max_value(self):
        return charging_current_limit(self.coordinator.data)

    @property
    def native_value(self):
        value = self.coordinator.data.get("150")
        return value if type(value) is int else None

    @property
    def available(self):
        return super().available and self.native_value is not None

    async def async_set_native_value(self, value):
        if not self.available or not self.native_min_value <= value <= self.native_max_value or value % 1:
            raise HomeAssistantError("Choose a whole ampere value within the charging current range")
        await self.coordinator.set_dp("150", int(value))
