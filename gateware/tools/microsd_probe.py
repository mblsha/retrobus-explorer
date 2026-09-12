#!/usr/bin/env python3
"""Read the input-only Arty microSD pin probe. No command drives the SD bus."""

from __future__ import annotations

import argparse
import json
import struct
import time
import zlib
from pathlib import Path

PMOD_PINS = (1, 2, 3, 4, 7, 8, 9, 10)
PROFILES = {
    "bottom-header": {"DAT2": 7, "DAT3": 8, "CMD": 9, "CLK": 3, "DAT0": 10, "DAT1": 4},
    "top-header-r180": {
        "DAT2": 4,
        "DAT3": 10,
        "CMD": 3,
        "CLK": 9,
        "DAT0": 8,
        "DAT1": 7,
    },
    "bottom-header-row-swap": {
        "DAT2": 1,
        "DAT3": 2,
        "CMD": 3,
        "CLK": 9,
        "DAT0": 4,
        "DAT1": 10,
    },
}


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ (7 if crc & 128 else 0)) & 255
    return crc


def request(opcode: int, sequence: int) -> bytes:
    if opcode not in (1, 2) or not 0 <= sequence <= 255:
        raise ValueError("Invalid opcode or sequence")
    body = bytes((1, opcode, sequence))
    return b"\xa5" + body + bytes((crc8(body), 0x5A))


def decode(packet: bytes) -> dict:
    if len(packet) != 64 or packet[:3] != b"MP\x01":
        raise ValueError("Invalid probe response header/length")
    if zlib.crc32(packet[:60]) != int.from_bytes(packet[60:], "little"):
        raise ValueError("Probe response CRC32 mismatch")
    if packet[55] not in range(len(PROFILES)) or packet[3] not in (1, 2):
        raise ValueError("Unknown probe profile/opcode")
    profile = tuple(PROFILES)[packet[55]]
    counts = struct.unpack_from("<8I", packet, 12)
    logical = {}
    for signal, pin in PROFILES[profile].items():
        index = PMOD_PINS.index(pin)
        logical[signal] = {
            "pmod_pin": pin,
            "level": (packet[5] >> index) & 1,
            "seen_high": bool(packet[6] & (1 << index)),
            "seen_low": bool(packet[7] & (1 << index)),
            "transitions": counts[index],
            "saturated": bool(packet[54] & (1 << index)),
            # Activity cannot prove physical identity; independent stimulus is required.
            "pinout_verified": False,
        }
    command = int.from_bytes(packet[44:50], "little")
    return {
        "schema": "microsd-probe-v1",
        "opcode": packet[3],
        "sequence": packet[4],
        "profile": profile,
        "cycles_mod_2_32": int.from_bytes(packet[8:12], "little"),
        "raw_levels": packet[5],
        "raw_transitions": list(counts),
        "signals": logical,
        "valid_sd_commands": int.from_bytes(packet[50:54], "little"),
        "last_command_hex": f"{command:012x}",
        "sd_outputs": "input-only",
        "verification": "observation-only; correlate with independent host stimulus",
    }


def exchange(port, opcode: int, sequence: int, timeout: float = 2.0) -> dict:
    port.write(request(opcode, sequence))
    port.flush()
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    while time.monotonic() < deadline:
        buffer.extend(port.read(64))
        while len(buffer) >= 64:
            try:
                result = decode(bytes(buffer[:64]))
            except ValueError:
                del buffer[0]
                continue
            del buffer[:64]
            if result["sequence"] == sequence and result["opcode"] == opcode:
                return result
    raise TimeoutError(
        "No valid matching probe response (check bitstream, port and baud)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Explicit macOS UART device")
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear observations before the sampling interval",
    )
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 3600:
        parser.error("--seconds must be in [0,3600]")
    import serial

    with serial.Serial(args.port, 1_000_000, timeout=0.1) as port:
        status = exchange(port, 1, 0)
        if status["profile"] != args.profile:
            raise SystemExit(f"Wrong bitstream profile: {status['profile']}")
        if args.clear:
            exchange(port, 2, 1)
        started = time.time()
        time.sleep(args.seconds)
        result = exchange(port, 1, 2)
    result.update(started_at=started, finished_at=time.time(), port=args.port)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
