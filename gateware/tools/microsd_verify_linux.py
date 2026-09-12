#!/usr/bin/env python3
"""Read-only hardware check of the small deterministic SPADE test image.

Run on the GKD over SSH, after enumeration. This requires Linux O_DIRECT and
validates the exact external controller, card identity, read-only state, clock,
width, and lack of mounts before opening the block device.
"""

import argparse
from microsd_qualify_linux import qualification
import hashlib
import json
import os
from microsd_host import validate_target, direct_read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    parser.add_argument(
        "--writable-card",
        action="store_true",
        help="Expect writable SPADE media but perform reads only",
    )
    parser.add_argument("--capacity-mib", type=int, choices=(8, 256), default=8)
    parser.add_argument("--clock-hz", type=int, default=1_000_000)
    parser.add_argument(
        "--actual-clock-hz",
        type=int,
        help="Expected divider output; defaults to requested clock",
    )
    args = parser.parse_args()
    with qualification(args):
        capacity = args.capacity_mib << 20
        ios, card = validate_target(
            args.bus_width,
            capacity,
            args.clock_hz,
            args.actual_clock_hz,
            writable=args.writable_card,
        )
        fd = os.open("/dev/mmcblk1", os.O_RDONLY | os.O_DIRECT)
        checks = []
        try:
            for offset, size in [
                (0, 512),
                (127 * 512, 512),
                (128 * 512, 512),
                (capacity - 512, 512),
                (capacity // 2, 512),
                (0, 65536),
                (120 * 512, 8192),
            ]:
                data = direct_read(fd, offset, size)
                expected = bytes(
                    (i * 37 + (i >> 8) * 11 + 17) & 255 if i < 65536 else 0
                    for i in range(offset, offset + size)
                )
                if data != expected:
                    raise RuntimeError((offset, size, "data mismatch"))
                checks.append(
                    dict(
                        offset=offset,
                        bytes=size,
                        sha256=hashlib.sha256(data).hexdigest(),
                        passed=True,
                    )
                )
        finally:
            os.close(fd)
        print(
            json.dumps(
                dict(
                    ios=ios,
                    cid=(card / "cid").read_text().strip(),
                    csd=(card / "csd").read_text().strip(),
                    scr=(card / "scr").read_text().strip(),
                    checks=checks,
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
