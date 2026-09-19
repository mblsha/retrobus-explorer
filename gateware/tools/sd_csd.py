#!/usr/bin/env python3
"""Build and read the card-specific data the microSD emulator advertises.

`experiments/openxc7-macos/build_ddr.py` bakes a CSD register into the
bitstream and the emulator hands that register back verbatim in its CMD9
response, so the register is the card's contract with the host. TRAN_SPEED
decides which clock the host then selects, and it shares the register with the
CRC7 protecting it, so editing one by hand without the other produces a card
the host rejects. The build therefore asks for a transfer rate in hertz and
gets a consistent register back from here.

TRAN_SPEED is one byte: bits [2:0] name the unit, bits [6:3] index a fixed
table of mantissas, and bit 7 is reserved. Only the rates that table can name
exist, which is why `tran_speed_code` refuses anything else instead of
silently advertising a neighbouring speed.
"""

# The supported card contract is checked against actual CMD9 responses by
# the Spade testbench, rather than inferred from the source's formatting.
SD_CSD = 0x0026001A115903FFC002800002400023

TRAN_SPEED_UNITS_HZ = (100_000, 1_000_000, 10_000_000, 100_000_000)
# Tenths, so every rate the encoding can name stays an exact integer. Index
# zero is reserved rather than a mantissa of nought.
TRAN_SPEED_MANTISSAS_TENTHS = (
    0, 10, 12, 13, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80,
)


def tran_speed_hz(code: int) -> int:
    """Return the bits per second a TRAN_SPEED byte advertises."""
    if not 0 <= code <= 0xFF:
        raise ValueError(f"TRAN_SPEED is a single byte, got {code:#x}")
    if code & 0x80:
        raise ValueError(f"TRAN_SPEED {code:#04x} sets the reserved bit 7")
    unit, mantissa = code & 7, code >> 3 & 15
    if unit >= len(TRAN_SPEED_UNITS_HZ):
        raise ValueError(f"TRAN_SPEED {code:#04x} names the reserved unit {unit}")
    if mantissa == 0:
        raise ValueError(f"TRAN_SPEED {code:#04x} names the reserved mantissa 0")
    return TRAN_SPEED_UNITS_HZ[unit] * TRAN_SPEED_MANTISSAS_TENTHS[mantissa] // 10


def _codes_by_rate() -> dict[int, int]:
    """Every rate the encoding can name, mapped to the byte that names it."""
    codes = {}
    for unit in range(len(TRAN_SPEED_UNITS_HZ)):
        for mantissa in range(1, len(TRAN_SPEED_MANTISSAS_TENTHS)):
            code = mantissa << 3 | unit
            codes[tran_speed_hz(code)] = code
    return codes


# The mantissas span one decade and the units step by decades, so no rate has
# two encodings; a collision here would mean the table above is wrong.
TRAN_SPEED_CODES = _codes_by_rate()
assert len(TRAN_SPEED_CODES) == 4 * 15


def tran_speed_code(hz: int) -> int:
    """Return the TRAN_SPEED byte advertising exactly `hz` bits per second.

    A rate the encoding cannot name is refused rather than rounded, because
    rounding down loses bandwidth silently and rounding up advertises a clock
    the emulator has not been qualified at.
    """
    code = TRAN_SPEED_CODES.get(hz)
    if code is not None:
        return code
    rates = sorted(TRAN_SPEED_CODES)
    neighbours = [f"below {rate}" for rate in rates if rate < hz][-1:]
    neighbours += [f"above {rate}" for rate in rates if rate > hz][:1]
    raise ValueError(
        f"{hz} bit/s is not an encodable SD TRAN_SPEED; the nearest "
        f"encodable rates are {', '.join(neighbours)}"
    )


def csd_crc7(data: bytes) -> int:
    crc = 0
    for byte in data:
        for bit in range(8):
            crc <<= 1
            if ((byte << bit) & 0x80) ^ (crc & 0x80):
                crc ^= 0x09
            crc &= 0x7F
    return crc


def sd_csd_with_speed(code: int) -> int:
    body = bytearray(SD_CSD.to_bytes(16, "big"))
    body[3] = code
    body[15] = (csd_crc7(bytes(body[:15])) << 1) | 1
    return int.from_bytes(bytes(body), "big")


def sd_properties(sd_csd: int = SD_CSD) -> dict:
    """Describe a CSD the way the build manifest records it."""
    return dict(
        sd_csd=f"{sd_csd:032x}",
        sd_capacity_bytes=(((sd_csd >> 62) & 4095) + 1)
        * (1 << (((sd_csd >> 47) & 7) + 2))
        * (1 << ((sd_csd >> 80) & 15)),
        sd_max_clock_hz=tran_speed_hz((sd_csd >> 96) & 255),
    )
