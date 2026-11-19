"""Cloud account and child charger configuration helpers."""

from .const import DOMAIN


def configured_devices(hass):
    """Return devices configured locally or under a cloud account."""
    return {
        device_id
        for entry in hass.config_entries.async_entries(DOMAIN)
        for device_id in (
            entry.data.get("device_id"),
            *(child.unique_id for child in entry.subentries.values()),
        )
        if device_id
    }
