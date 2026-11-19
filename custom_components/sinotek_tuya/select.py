"""Current settings using the actual advertised amperage choices."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

from .entity import ChargerEntity
from .profile import current_choices


async def async_setup_entry(hass, entry, async_add_entities):
    for coordinator in entry.runtime_data:
        def add(entities, subentry=coordinator.subentry):
            async_add_entities(entities, config_subentry_id=subentry.subentry_id if subentry else None)
        setup_charger(hass, entry, coordinator, add)


def setup_charger(hass, entry, coordinator, async_add_entities):
    entities = [CurrentSelect(coordinator, "152", "Maximum Charging Current")]
    # Keep legacy automations and dashboard cards working after the UI switches to number.
    registry = er.async_get(hass)
    legacy_id = registry.async_get_entity_id("select", DOMAIN, f"{coordinator.device_id}_150")
    if legacy_id is not None:
        legacy = registry.async_get(legacy_id)
        if legacy.hidden_by is None:
            registry.async_update_entity(legacy_id, hidden_by=er.RegistryEntryHider.INTEGRATION)
        entities.append(CurrentSelect(coordinator, "150", "Charging Current"))
    async_add_entities(entities)


class CurrentSelect(ChargerEntity, SelectEntity):
    """Expose only model-supported current settings."""

    def __init__(self, coordinator, dp, name):
        super().__init__(coordinator, dp, name)
        self.dp = dp

    @property
    def options(self):
        return [f"{n} A" for n in current_choices(self.coordinator.data, self.dp)]

    @property
    def available(self):
        return super().available and bool(self.options) and type(self.coordinator.data.get(self.dp)) is int

    @property
    def current_option(self):
        option = f"{self.coordinator.data.get(self.dp)} A"
        return option if option in self.options else None

    async def async_select_option(self, option):
        if option not in self.options:
            raise HomeAssistantError("This current is no longer available")
        await self.coordinator.set_dp(self.dp, int(option.split()[0]))
