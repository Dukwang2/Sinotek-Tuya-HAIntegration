"""Shared identity for charger entities."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class ChargerEntity(CoordinatorEntity):
    """Attach all public readings and controls directly to the charger."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        device_id = coordinator.device_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=coordinator.name,
            manufacturer="Sinotek",
            model="Tuya EV Charger",
        )
