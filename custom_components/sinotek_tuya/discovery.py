"""Collect passive and solicited Tuya discovery on HA's enabled interfaces."""

import json
import logging
import selectors
import socket
import time

import tinytuya
from tinytuya.scanner import send_discovery_request

_LOGGER = logging.getLogger(__name__)


def discover(interfaces, duration=5, target=None):
    """Return local discovery records keyed by full device ID."""
    found = {}
    requests = {address: {"broadcast": broadcast} for address, broadcast in interfaces}
    with selectors.DefaultSelector() as selector:
        listeners = []
        try:
            for port in (6666, 6667, 7000):
                listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                listeners.append(listener)
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    listener.bind(("", port))
                except OSError:
                    _LOGGER.debug("Tuya discovery port %s already occupied", port)
                    continue
                selector.register(listener, selectors.EVENT_READ)
            if requests:
                send_discovery_request(requests)
            for request in requests.values():
                if "socket" in request:
                    selector.register(request["socket"], selectors.EVENT_READ)
            deadline = time.monotonic() + duration
            while selector.get_map() and (remaining := deadline - time.monotonic()) > 0:
                for event, _ in selector.select(remaining):
                    packet, (host, _) = event.fileobj.recvfrom(8192)
                    try:
                        data = json.loads(tinytuya.decrypt_udp(packet))
                        device_id = data.get("gwId")
                        version = str(data.get("version", ""))
                    except (ValueError, TypeError, AttributeError, OSError):
                        continue
                    if device_id and version in ("3.1", "3.2", "3.3", "3.4", "3.5"):
                        found[device_id] = {"host": host, "version": version}
                        if device_id == target:
                            return found
        finally:
            for listener in listeners:
                listener.close()
            for request in requests.values():
                if "socket" in request:
                    request["socket"].close()
    return found


async def interfaces(hass):
    """Use HA's selected adapters, including their actual IPv4 prefixes."""
    from ipaddress import IPv4Interface
    from homeassistant.components import network

    return [
        (str(interface.ip), str(interface.network.broadcast_address))
        for adapter in await network.async_get_adapters(hass)
        if adapter["enabled"]
        for address in adapter["ipv4"]
        if not (interface := IPv4Interface(
            (address["address"], address["network_prefix"])
        )).ip.is_loopback
        and interface.network.prefixlen < 31
    ]
