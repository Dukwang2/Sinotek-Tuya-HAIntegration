"""Read Sinotek tariff and schedule packets after checking length and CRC."""

import base64
import binascii

SCHEDULE_BLOCKS = {
    "194": ("Weekday", 0), "195": ("Weekday", 6),
    "180": ("Weekday", 12), "181": ("Weekday", 18),
    "196": ("Weekend", 0), "197": ("Weekend", 6),
    "182": ("Weekend", 12), "183": ("Weekend", 18),
}
TARIFF_BANDS = ("Peak", "Mid-peak", "Off-peak", "Super off-peak")


def crc8(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ (7 if crc & 128 else 0)) & 255
    return crc


def packet(value, size):
    if not isinstance(value, str):
        return None
    for decoder in (bytes.fromhex, lambda text: base64.b64decode(text, validate=True)):
        try:
            data = decoder(value)
        except (ValueError, binascii.Error):
            continue
        if len(data) == size and crc8(data[:-1]) == data[-1]:
            return data[:-1]
    return None


def schedule_readings(dps):
    """Yield concise, readable settings without publishing packet content."""
    for dp, (day, start) in SCHEDULE_BLOCKS.items():
        data = packet(dps.get(dp), 13)
        if data is None or any(value > 64 for value in data):
            continue
        slots = []
        for i, value in enumerate(data):
            hour, minute = start + i // 2, 30 * (i % 2)
            action = "Off" if value == 0 else "Keep" if value < 6 else f"{value} A"
            slots.append(f"{hour:02}:{minute:02} {action}")
        yield f"{day} Schedule {start:02}:00", ", ".join(slots)
    for day, rate_dp, slot_dp in (("Weekday", "190", "191"), ("Weekend", "192", "193")):
        data = packet(dps.get(rate_dp), 11)
        if data is not None:
            for i, band in enumerate(TARIFF_BANDS):
                yield f"{day} {band} Tariff", int.from_bytes(data[2*i:2*i+2], "little") / 100
        slots = packet(dps.get(slot_dp), 13)
        if slots is not None:
            codes = [part for byte in slots for part in (byte >> 4, byte & 15)]
            if all(1 <= code <= 4 for code in codes):
                for start in (0, 12):
                    bands = " / ".join(TARIFF_BANDS[code - 1] for code in codes[start:start + 12])
                    yield f"{day} Tariff Bands {start:02}:00", bands
