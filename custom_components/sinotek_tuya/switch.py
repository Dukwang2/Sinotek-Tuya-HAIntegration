"""State-backed charging switches."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .entity import ChargerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    for coordinator in entry.runtime_data:
        def add(entities, subentry=coordinator.subentry):
            async_add_entities(entities, config_subentry_id=subentry.subentry_id if subentry else None)
        setup_charger(hass, entry, coordinator, add)


def setup_charger(hass, entry, coordinator, async_add_entities):
    async_add_entities([
        ChargerSwitch(coordinator, "140", "Start or Pause Charging"),
        ChargerSwitch(coordinator, "154", "Require Charging Approval"),
    ])
    phase_switch_added = False

    @callback
    def add_phase_switch():
        nonlocal phase_switch_added
        if not phase_switch_added and isinstance(coordinator.data.get("122"), bool):
            phase_switch_added = True
            async_add_entities([SinglePhaseSwitch(coordinator, "122", "Single-phase Mode")])

    entry.async_on_unload(coordinator.async_add_listener(add_phase_switch))
    add_phase_switch()


class ChargerSwitch(ChargerEntity, SwitchEntity):
    """A toggle that uses the actual firmware readback."""

    def __init__(self, coordinator, dp, name):
        super().__init__(coordinator, dp, name)
        self.dp = dp

    @property
    def is_on(self):
        state = self.coordinator.data.get(self.dp)
        return state if isinstance(state, bool) else None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.set_dp(self.dp, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.set_dp(self.dp, False)


class SinglePhaseSwitch(ChargerSwitch):
    """Expose the phase setting only on chargers that report it."""

    @property
    def available(self):
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs):
        if not self.available:
            raise HomeAssistantError("Single-phase mode is unavailable")
        await super().async_turn_on(**kwargs)

    async def async_turn_off(self, **kwargs):
        if not self.available:
            raise HomeAssistantError("Single-phase mode is unavailable")
        await super().async_turn_off(**kwargs)
