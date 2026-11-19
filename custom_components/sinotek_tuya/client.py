"""TinyTuya transport and setup credential sources."""

from contextlib import contextmanager
import json

import tinytuya


class DeviceError(Exception):
    """The charger did not accept or answer a local query."""


@contextmanager
def connection(device_id, host, local_key, version, **kwargs):
    device = tinytuya.Device(device_id, host, local_key, version=float(version), **kwargs)
    device.set_socketTimeout(3)
    device.set_socketRetryLimit(1)
    try:
        yield device
    finally:
        device.close()


def read(device_id, host, local_key, version):
    with connection(device_id, host, local_key, version) as device:
        response = device.status()
    if not isinstance(response, dict) or not isinstance(response.get("dps"), dict):
        raise DeviceError("Tuya status query failed")
    if not response["dps"]:
        raise DeviceError("Tuya status query returned no data")
    return response["dps"]


def write(device_id, host, local_key, version, dp, value):
    with connection(device_id, host, local_key, version) as device:
        response = device.set_value(dp, value)
    if not isinstance(response, dict) or "Error" in response:
        raise DeviceError("Tuya write was not acknowledged")


def import_devices(payload):
    """Read TinyTuya wizard exports or an ID-keyed device object."""
    rows = json.loads(payload)
    if isinstance(rows, dict):
        rows = [
            {"id": device_id, **row}
            for device_id, row in rows.items()
            if isinstance(row, dict)
        ]
    if not isinstance(rows, list):
        raise ValueError("Expected a device list")
    devices = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("key") or row.get("local_key")
        if row.get("id") and isinstance(key, str) and len(key.encode()) == 16:
            devices[row["id"]] = {
                "local_key": key,
                "name": row.get("name") or "Sinotek Charger",
                "host": row.get("ip") or "",
                "version": str(row.get("version", "")),
            }
    if not devices:
        raise ValueError("No usable device keys")
    return devices


def cloud_devices(region, access_id, secret, user_id):
    """Fetch the linked account's device keys using its Tuya user ID."""
    from urllib.parse import quote

    if not all(value.strip() for value in (access_id, secret, user_id)):
        raise ValueError("Cloud API credentials and User ID are required")
    cloud = tinytuya.Cloud(
        apiRegion=region, apiKey=access_id.strip(), apiSecret=secret.strip()
    )
    response = cloud.cloudrequest(
        f"/v1.0/users/{quote(user_id.strip(), safe='')}/devices"
    )
    if not isinstance(response, dict) or not response.get("success"):
        raise ValueError("Tuya Cloud did not return the linked account's devices")
    devices = import_devices(json.dumps(response.get("result")))
    # Cloud IP is the public egress address, not a LAN endpoint.
    for device in devices.values():
        device["host"] = ""
    return devices
