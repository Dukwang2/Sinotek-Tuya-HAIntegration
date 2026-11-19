"""Sinotek charger integration."""

import asyncio
from datetime import timedelta
import logging
from time import monotonic

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import client
from .const import PLATFORMS
from .discovery import discover, interfaces
from .profile import is_charger

_LOGGER = logging.getLogger(__name__)


class ChargerCoordinator(DataUpdateCoordinator):
    """Serialize local queries and commands, and rediscover changed IPs."""

    def __init__(self, hass, entry, subentry=None):
        super().__init__(hass, _LOGGER, config_entry=entry, name=subentry.title if subentry else entry.title,
                         update_interval=timedelta(seconds=10))
        self.subentry = subentry
        self.connection_data = subentry.data if subentry else entry.data
        self.device_id = self.connection_data["device_id"]
        self.host = self.connection_data["host"]
        self.lock = asyncio.Lock()
        self.next_discovery = 0
        self.charger_identified = False
        self.data = {}

    @property
    def address(self):
        data = self.connection_data
        return data["device_id"], self.host, data["local_key"], data["version"]

    def accept_readings(self, data):
        self.charger_identified |= is_charger(data)
        return data

    async def _async_update_data(self):
        async with self.lock:
            try:
                return self.accept_readings(
                    await self.hass.async_add_executor_job(client.read, *self.address)
                )
            except (client.DeviceError, ValueError, OSError) as error:
                if monotonic() < self.next_discovery:
                    raise UpdateFailed("Charger unavailable") from error
                self.next_discovery = monotonic() + 60
            found = await self.hass.async_add_executor_job(
                discover, await interfaces(self.hass), 4, self.device_id
            )
            record = found.get(self.device_id)
            if not record:
                raise UpdateFailed("Charger unavailable on the local network")
            device_id, _, key, version = self.address
            try:
                data = await self.hass.async_add_executor_job(
                    client.read, device_id, record["host"], key, version
                )
            except (client.DeviceError, ValueError, OSError) as error:
                raise UpdateFailed("Discovered charger did not authenticate") from error
            self.host = record["host"]
            if self.host != self.connection_data["host"]:
                self.connection_data = {**self.connection_data, "host": self.host}
                # Subentry updates notify the hub listener and would reload all chargers.
                # Keep rediscovery in memory until the user saves a reconfiguration.
                if self.subentry is None:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=self.connection_data
                    )
            return self.accept_readings(data)

    async def set_dp(self, dp, value):
        async with self.lock:
            if not self.last_update_success:
                raise HomeAssistantError("Charger is unavailable")
            if not self.charger_identified:
                raise HomeAssistantError("The charger has not reported the expected control profile")
            try:
                await self.hass.async_add_executor_job(client.write, *self.address, dp, value)
            except (client.DeviceError, ValueError, OSError) as error:
                raise HomeAssistantError("Charger did not acknowledge the command") from error
        await self.async_request_refresh()


async def reload_cloud_account(hass, entry):
    """Reload after account or subentry configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry):
    if entry.data.get("kind") == "cloud":
        coordinators = [
            ChargerCoordinator(hass, entry, subentry)
            for subentry in entry.subentries.values()
        ]
        await asyncio.gather(*(coordinator.async_refresh() for coordinator in coordinators))
        entry.async_on_unload(entry.add_update_listener(reload_cloud_account))
    else:
        coordinator = ChargerCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        coordinators = [coordinator]
    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
