#!/usr/bin/env python3
"""Load a bounded 64 KiB prefix or query the SD emulator over UART."""

import argparse
import struct
import time
import zlib
from pathlib import Path


def open_port(path):
    import serial

    # Arty can connect a USB-UART modem-control signal to CK_RST through JP2.
    # Configure inactive modem lines before opening, rather than asserting
    # pyserial's default DTR/RTS and changing them after the port is open.
    port = serial.Serial(port=None, baudrate=1_000_000, timeout=0.05)
    port.dtr = False
    port.rts = False
    port.port = path
    port.open()
    return port


def packet(opcode, sector, sequence, data=bytes(512)):
    if (
        opcode not in (1, 2, 3, 4)
        or not 0 <= sector < 128
        or not 0 <= sequence <= 0xFFFFFFFF
        or len(data) != 512
    ):
        raise ValueError("Invalid image packet")
    body = struct.pack("<4sB3xII", b"MSD1", opcode, sector, sequence) + data
    return body + struct.pack("<I", zlib.crc32(body))


def decode_ack(data):
    if (
        len(data) != 16
        or data[:4] != b"MSA1"
        or zlib.crc32(data[:12]) != int.from_bytes(data[12:], "little")
    ):
        raise ValueError("Invalid image acknowledgement")
    opcode, status, sequence = struct.unpack("<BB2xI", data[4:12])
    return opcode, status, sequence


def exchange(port, opcode, sector, sequence, data=bytes(512)):
    message = packet(opcode, sector, sequence, data)
    for _ in range(3):
        port.write(message)
        port.flush()
        deadline = time.monotonic() + 2
        buffer = bytearray()
        while time.monotonic() < deadline:
            buffer.extend(port.read(16))
            while len(buffer) >= 16:
                if buffer[:4] != b"MSA1":
                    del buffer[0]
                    continue
                try:
                    op, status, seq = decode_ack(bytes(buffer[:16]))
                except ValueError:
                    del buffer[0]
                    continue
                del buffer[:16]
                if op == opcode and (seq == sequence or opcode == 4):
                    if status:
                        raise RuntimeError(f"Loader rejected command: status {status}")
                    return seq if opcode == 4 else None
    raise TimeoutError(
        f"No valid loader acknowledgement after three attempts "
        f"(opcode={opcode}, sector={sector}, sequence={sequence})"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("image", type=Path, nargs="?")
    p.add_argument("--port", required=True)
    p.add_argument("--no-arm", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument(
        "--clock-status", action="store_true", help="Read input-only SD clock counters"
    )
    p.add_argument("--system-clock-hz", type=int, default=80_000_000)
    p.add_argument(
        "--diagnostics",
        action="store_true",
        help="Read stable BIST mismatch detail after failure",
    )
    args = p.parse_args()
    if args.clock_status:
        import json

        with open_port(args.port) as port:
            peak = exchange(port, 4, 120, 120) >> 5
            shortest = exchange(port, 4, 121, 121) >> 5
            latest = exchange(port, 4, 122, 122) >> 5
            for _ in range(3):
                high = exchange(port, 4, 124, 124) >> 5
                low = exchange(port, 4, 123, 123) >> 5
                high_after = exchange(port, 4, 124, 124) >> 5
                if high == high_after:
                    break
            else:
                raise RuntimeError("Clock counter did not give a consistent snapshot")
        print(
            json.dumps(
                dict(
                    peak_edges_per_ms=peak,
                    peak_window_clock_hz=peak * 1000,
                    # A single period is quantized to management cycles.
                    # Use the 1 ms edge count for non-integer clock ratios.
                    shortest_period_cycles=shortest,
                    latest_period_cycles=latest,
                    latest_clock_hz=args.system_clock_hz / latest if latest else None,
                    total_edges=(high << 27) | low,
                ),
                indent=2,
            )
        )
        return
    if args.diagnostics:
        import json

        with open_port(args.port) as port:
            status = exchange(port, 4, 0, 0)
            if not status & 128:
                raise RuntimeError("Detailed snapshot requires a stopped, failed BIST")
            if exchange(port, 4, 127, 127) >> 5 != 0x534244:
                raise RuntimeError(
                    "This bitstream does not support BIST detail format 1"
                )
            detail = sum(
                (exchange(port, 4, i, i) >> 5) << ((i - 1) * 27) for i in range(1, 12)
            )
            after = exchange(port, 4, 0, 12)
            if after != status:
                raise RuntimeError("BIST status changed during diagnostic read")
        actual = (detail >> 32) & ((1 << 128) - 1)
        expected = (detail >> 160) & ((1 << 128) - 1)
        address = detail & 0xFFFFFF
        print(
            json.dumps(
                dict(
                    status=f"0x{status:08x}",
                    native_word=address,
                    byte_address=address * 16,
                    actual=f"{actual:032x}",
                    expected=f"{expected:032x}",
                    xor=f"{actual ^ expected:032x}",
                ),
                indent=2,
            )
        )
        return
    if args.status:
        with open_port(args.port) as port:
            bits = exchange(port, 4, 0, 0)
        print(
            f"status=0x{bits:08x}; initialized={bool(bits & 1)} cmd_ready={bool(bits & 2)} wdata_ready={bool(bits & 4)} armed={bool(bits & 8)} rdata_valid={bool(bits & 16)}"
        )
        print(
            f"bist_busy={bool(bits & 32)} bist_passed={bool(bits & 64)} "
            f"bist_failed={bool(bits & 128)} bist_sector={(bits >> 8) & 0x7FFFF} bist_phase={(bits >> 27) & 7} bist_error={bits >> 30}"
        )
        return
    if args.image is None:
        p.error("image is required unless --status is used")
    data = args.image.read_bytes()
    if not 0 < len(data) <= 65536:
        p.error("Image must contain 1..65536 bytes")
    data = data.ljust(65536, b"\0")
    with open_port(args.port) as port:
        exchange(port, 3, 0, 0)
        for sector in range(128):
            exchange(
                port, 1, sector, sector + 1, data[sector * 512 : (sector + 1) * 512]
            )
        if not args.no_arm:
            exchange(port, 2, 0, 129)
    print(
        f"Loaded 65536 resident bytes; CRC32 {zlib.crc32(data):08x}; armed={not args.no_arm}"
    )


if __name__ == "__main__":
    main()
