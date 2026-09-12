#!/usr/bin/env python3
"""Verified sustained reads of the BIST-zeroed card plus 64 KiB UART prefix.

Use only before host writes, immediately after loading one-bit-image.bin.
Controller errors and hidden recovery are checked automatically.
"""

import argparse
from microsd_qualify_linux import qualification
import hashlib
import json
import mmap
import os
import time
from microsd_host import validate_target, read_into


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clock-hz", type=int, required=True)
    p.add_argument("--actual-clock-hz", type=int, required=True)
    p.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    p.add_argument("--span-mib", type=int, default=16)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument(
        "--request-kib", type=int, choices=(4, 16, 64, 256, 1024), default=64
    )
    a = p.parse_args()
    with qualification(a):
        if not (1 <= a.span_mib <= 256 and 1 <= a.repeats <= 10):
            raise RuntimeError(
                "Check failed: 1 <= a.span_mib <= 256 and 1 <= a.repeats <= 10"
            )
        validate_target(a.bus_width, 256 << 20, a.clock_hz, a.actual_clock_hz)
        size = a.span_mib << 20
        request_bytes = a.request_kib << 10
        prefix = bytes((i * 37 + (i >> 8) * 11 + 17) & 255 for i in range(65536))
        expected = hashlib.sha256(prefix)
        zero = bytes(65536)
        for _ in range(65536, size, 65536):
            expected.update(zero)
        expected = expected.hexdigest()
        results = []
        fd = os.open("/dev/mmcblk1", os.O_RDONLY | os.O_DIRECT)
        try:
            with mmap.mmap(-1, request_bytes) as buf:
                for repeat in range(a.repeats):
                    digest = hashlib.sha256()
                    io_seconds = 0.0
                    start = time.monotonic()
                    for offset in range(0, size, request_bytes):
                        io_start = time.monotonic()
                        read_into(fd, buf, offset)
                        io_seconds += time.monotonic() - io_start
                        digest.update(buf)
                    elapsed = time.monotonic() - start
                    if digest.hexdigest() != expected:
                        raise RuntimeError("read data digest mismatch")
                    results.append(
                        dict(
                            repeat=repeat,
                            bytes=size,
                            seconds=elapsed,
                            bytes_per_second=size / elapsed,
                            io_bytes_per_second=size / io_seconds,
                            sha256=digest.hexdigest(),
                        )
                    )
        finally:
            os.close(fd)
        print(
            json.dumps(
                dict(passed=True, configuration=vars(a), results=results), indent=2
            )
        )


if __name__ == "__main__":
    main()
