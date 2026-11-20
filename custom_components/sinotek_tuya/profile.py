"""Readable Sinotek datapoints based on ha_dp_definitions.md."""

import json

from .schedule import schedule_readings

STATES = {
    100: "Offline", 101: "Waiting for plug", 102: "Sleeping",
    200: "Standby", 201: "Complete", 202: "Waiting for schedule",
    203: "Waiting for delay", 204: "Paused", 205: "Approval required",
    206: "Household overload", 300: "Charging", 315: "Charging from home outlet",
    320: "Charging from NEMA 6-20", 330: "Charging from campground outlet",
    340: "Charging from dryer outlet", 350: "Charging from high-power outlet",
    360: "Charging at reduced current", 370: "Charging with load balancing",
    400: "Overcurrent", 401: "Overvoltage", 402: "Undervoltage",
    403: "Control box overheating", 404: "Wall plug overheating",
    405: "Connector overheating", 500: "Self-test failure", 501: "Leakage detected",
    502: "Stuck relay", 503: "RCD failure", 504: "Control pilot failure",
    505: "Other fault", 506: "EV diode missing", 507: "Ground missing",
}
MODES = {0: "Immediate", 1: "Delayed", 2: "Scheduled", 3: "Solar Only"}
PLUGS = dict(enumerate((
    "Unspecified", "Home outlet", "Campground", "NEMA 6-20",
    "Dryer outlet", "High-power outlet", "CEE 32 A three-phase",
    "CEE 16 A three-phase", "CEE 32 A single-phase", "Strong outlet",
    "Household outlet", "Limited outlet", "Gentle outlet", "Extra gentle",
), 1))
CP_STATES = {
    "STATE_A": "Vehicle disconnected", "STATE_B": "Vehicle connected",
    "STATE_C": "Vehicle requesting charge", "SLEEP": "Sleeping", "IDLE": "Idle",
    "IDLEINS": "Connected and idle", "WORKING": "Charging", "WAIT": "Waiting",
    "ERRORPAUSE": "Paused by fault", "PAUSE": "Paused", "STOP": "Stopped",
    "EMPTY": "No status",
}


def state_label(value):
    if type(value) is not int:
        return None
    return "Protection" if 406 <= value <= 499 else STATES.get(value, f"Unknown state ({value})")


def field(data, *path):
    for part in path:
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(part, int) and isinstance(data, list) and part < len(data):
            data = data[part]
        else:
            return None
    return data


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def is_charger(dps):
    return (
        type(dps.get("101")) is int
        and type(dps.get("150")) is int
        and isinstance(field(decode(dps.get("106")), "fv"), str)
    )


def current_choices(dps, dp):
    if dp == "150":
        return list(range(6, charging_current_limit(dps) + 1))
    choices = decode(dps.get("107"))
    if not isinstance(choices, list):
        return []
    return sorted({n for n in choices if type(n) is int and 6 <= n <= 32})


def charging_current_limit(dps):
    presets = current_choices(dps, "152")
    configured = dps.get("152")
    device_max = max(presets, default=32)
    if type(configured) is int and 6 <= configured <= 32:
        return min(device_max, configured)
    return device_max


def readings(dps):
    """Parse raw payloads once and expose typed, short-named readings."""
    def add(name, value, unit=None, cls=None):
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            result[name] = (value, unit, cls)

    def num(name, value, unit=None, cls=None, factor=1):
        if type(value) in (int, float):
            add(name, round(value * factor, 3), unit, cls)

    result = {}
    data = {k: decode(v) for k, v in dps.items()}
    m = data.get("102")
    mode = data.get("151")
    add("Charger State", state_label(dps.get("101")))
    add("Diagnostic Work State", CP_STATES.get(dps.get("109")))
    add("Charge Mode", MODES.get(field(mode, "m")))
    add("Market", {0: "US", 1: "EU"}.get(dps.get("114")))
    add("Plug Type", PLUGS.get(dps.get("160")))
    add("Last Alarm", state_label(field(data.get("104"), "v")))
    add("Active Phases", {0: "Single-phase", 1: "Three-phase"}.get(field(m, "p3")))
    add("Load Balancing", {0: "Disabled", 1: "Enabled"}.get(field(data.get("120"), "on")))
    variant = dps.get("157")
    if type(variant) is int:
        add("Product Capabilities", " / ".join((
            "Preset max current" if variant & 1 else "No preset max current",
            "NFC supported" if variant & 4 else "No NFC",
        )))
    contact = dps.get("116")
    if type(contact) is int:
        add("Customer Contact", f"Customer contact #{contact}" if contact else "No contact configured")
    choices = current_choices(dps, "152")
    if choices:
        add("Available Charging Currents", f"6–{charging_current_limit(dps)} A (1 A steps)")
    for name, value, unit, cls, factor in (
        ("Voltage", field(m, "L", 0), "V", "voltage", .1),
        ("Measured Current", field(m, "L", 1), "A", "current", .1),
        ("Power", field(m, "p") if field(m, "p") is not None else field(m, "L", 2), "kW", "power", .1),
        ("Reported Temperature", field(m, "t"), "°C", "temperature", .1),
        ("Session Duration", field(m, "d"), "s", "duration", .1),
        ("Session Energy", field(m, "e"), "kWh", "energy", .1),
        ("Session Cost", field(m, "c"), None, None, .01),
        ("Schedule Savings", field(m, "s"), None, None, .01),
        ("Control Pilot Voltage", field(m, "cp"), "V", "voltage", .1),
        ("Charge Mode Current", field(mode, "c"), "A", "current", 1),
        ("Charge Delay", field(mode, "dt"), "h", "duration", .5),
        ("Wi-Fi Signal", dps.get("110"), "dBm", "signal_strength", 1),
        ("NFC Card Count", field(data.get("112"), "n"), None, None, 1),
        ("Lifetime Sessions", field(data.get("115"), "d"), None, None, 1),
        ("Lifetime Energy", field(data.get("115"), "e"), "kWh", "energy", .1),
        ("Last Session Energy", field(data.get("105"), "c"), "kWh", "energy", .1),
        ("Last Session Duration", field(data.get("105"), "d"), "s", "duration", 1),
        ("Reported DP Count", field(data.get("117"), "dpn"), None, None, 1),
        ("DLB Service Current Limit", field(data.get("120"), "Lset"), "A", "current", 1),
    ):
        num(name, value, unit, cls, factor)
    for name, dp, key in (
        ("Firmware", "106", "fv"), ("RCD Type", "106", "r"),
        ("Last Self Test Time", "103", "t"), ("Last Alarm Time", "104", "t"),
        ("Last Session Start", "105", "t"), ("History Start Date", "115", "t"),
    ):
        add(name, field(data.get(dp), key))
    for i, name in enumerate(("Wall Plug", "Control Box", "EV Connector")):
        temp = field(data.get("113"), i)
        if type(temp) in (int, float) and temp <= 400:
            num(f"Temperature - {name}", temp, "°C", "temperature")
    for i, name in enumerate(("Ground", "Relay", "Leakage")):
        add(f"Self Test - {name}", {0: "Failed", 1: "Passed"}.get(field(data.get("103"), "r", i)))
    for i in range(3):
        phase = f"L{i + 1}"
        meter = data.get("121")
        current = field(meter, i)
        if meter != [-1, -1, -1] and type(current) is int and abs(current) <= 4000:
            num(f"Meter {phase} Current", current, "A", "current", .1)
        values = field(data.get("117"), phase)
        if values != [0, 0]:
            num(f"{phase} Voltage", field(values, 0), "V", "voltage", .1)
            num(f"{phase} Current", field(values, 1), "A", "current", .1)
    if isinstance(meter_id := dps.get("119"), str):
        add("Meter Binding", meter_id or "Unbound")
    if isinstance(debug := dps.get("153"), str) and debug.strip():
        add("Firmware Debug", debug[:255])
    if isinstance(legacy_current := dps.get("111"), str) and legacy_current.endswith("A"):
        add("Legacy Charging Current", legacy_current)
    if isinstance(nfc := dps.get("155"), bool):
        add("Legacy NFC Setting", "Enabled" if nfc else "Disabled")
    if type(temperature_mode := dps.get("161")) is int:
        add("Temperature Mode (reserved)", temperature_mode)
    if type(currency := dps.get("165")) is int and currency >= 0:
        add("Currency", {0: "$", 1: "€", 2: "£", 3: "¥"}.get(currency, "Custom"))
    for name, value in schedule_readings(dps):
        add(name, value)
    return result
