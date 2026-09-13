#!/usr/bin/env python3
"""Modify a bounded UART-uploaded prefix on the verified external FPGA SD card."""

import hashlib
import json
import argparse
from microsd_qualify_linux import qualification
import os
from microsd_host import direct_device, validate_target, direct_read, direct_write


def image_prefix():
    return bytes((i * 37 + (i >> 8) * 11 + 17) & 255 for i in range(65536))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus-width", type=int, choices=(1, 4), default=4)
    parser.add_argument("--clock-hz", type=int, default=13_000_000)
    parser.add_argument("--actual-clock-hz", type=int, default=12_913_043)
    args = parser.parse_args()
    with qualification(args):
        validate_target(args.bus_width, 256 << 20, args.clock_hz, args.actual_clock_hz)
        original = image_prefix()
        expected = bytearray(original)
        expected[4096:8192] = bytes(byte ^ 0xA5 for byte in expected[4096:8192])
        checks = []
        with direct_device(os.O_RDWR) as fd:
            if direct_read(fd, 0, len(original)) != original:
                raise RuntimeError("Uploaded prefix does not match the expected image")
            for offset in (65536, (256 << 20) - 4096):
                if direct_read(fd, offset, 4096) != bytes(4096):
                    raise RuntimeError("Expected zero-filled tail or final page")
            direct_write(fd, 4096, expected[4096:8192])
            os.fsync(fd)
            for _ in range(3):
                actual = direct_read(fd, 0, len(expected))
                if actual != expected:
                    raise RuntimeError("Modified prefix readback mismatch")
                checks.append(hashlib.sha256(actual).hexdigest())
            for offset in (65536, (256 << 20) - 4096):
                if direct_read(fd, offset, 4096) != bytes(4096):
                    raise RuntimeError("Expected zero-filled tail or final page")
        validate_target(args.bus_width, 256 << 20, args.clock_hz, args.actual_clock_hz)
        print(
            json.dumps(
                {
                    "verified_prefix_bytes": len(original),
                    "modified_offset": 4096,
                    "modified_bytes": 4096,
                    "before_sha256": hashlib.sha256(original).hexdigest(),
                    "after_sha256": hashlib.sha256(expected).hexdigest(),
                    "readback_sha256": checks,
                    "untouched_tail_and_last_page_zero": True,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
