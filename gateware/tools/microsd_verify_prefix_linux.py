#!/usr/bin/env python3
"""Modify a bounded UART-uploaded prefix on the verified external FPGA SD card."""

import hashlib
import json
import argparse
from microsd_qualify_linux import qualification
import os
from microsd_host import validate_target, direct_read, direct_write


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
        fd = os.open("/dev/mmcblk1", os.O_RDWR | os.O_DIRECT)
        checks = []
        try:

            def read(offset, size):
                return direct_read(fd, offset, size)

            if read(0, len(original)) != original:
                raise RuntimeError("Check failed: read(0, len(original)) == original")
            for offset in (65536, (256 << 20) - 4096):
                if read(offset, 4096) != bytes(4096):
                    raise RuntimeError(
                        "Check failed: read(offset, 4096) == bytes(4096)"
                    )
            direct_write(fd, 4096, expected[4096:8192])
            os.fsync(fd)
            for _ in range(3):
                actual = read(0, len(expected))
                if actual != expected:
                    raise RuntimeError("Check failed: actual == expected")
                checks.append(hashlib.sha256(actual).hexdigest())
            for offset in (65536, (256 << 20) - 4096):
                if read(offset, 4096) != bytes(4096):
                    raise RuntimeError(
                        "Check failed: read(offset, 4096) == bytes(4096)"
                    )
        finally:
            os.close(fd)
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
