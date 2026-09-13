#!/usr/bin/env python3
"""Bounded raw read/write check of the volatile SPADE DDR card on GKD.

Run only after DDR qualification and read-only checks have passed. This writes
small deterministic patterns to the FPGA test card and leaves them in place.
It refuses mounted media, a different card/controller, and an unexpected size.
"""

from microsd_qualify_linux import qualification
import hashlib
import json
import os

from microsd_host import (
    direct_device,
    target_parser,
    CAPACITY,
    CID,
    validate_target,
    direct_read,
    direct_write,
)


def write_cases(capacity):
    if capacity not in (8 * 1024 * 1024, 256 * 1024 * 1024):
        raise RuntimeError(
            "Check failed: capacity in (8 * 1024 * 1024, 256 * 1024 * 1024)"
        )
    return (
        (0, 512),
        (127 * 512, 512),
        (128 * 512, 512),
        (capacity - 512, 512),
        (1000 * 512, 8192),
        (120 * 512, 8192),
    )


CASES = write_cases(CAPACITY)


def expected_bytes(offset, size, iteration, capacity=CAPACITY):
    if not (0 <= offset and 0 < size and (offset + size <= capacity)):
        raise RuntimeError(
            "Check failed: 0 <= offset and 0 < size and (offset + size <= capacity)"
        )
    if not (offset % 512 == size % 512 == 0):
        raise RuntimeError("Check failed: offset % 512 == size % 512 == 0")
    if iteration not in (0, 1):
        raise RuntimeError("Check failed: iteration in (0, 1)")
    return bytes(
        ((i * 53 + (i >> 8) * 7 + 29) & 255) ^ (255 * iteration)
        for i in range(offset, offset + size)
    )


def main():
    parser = target_parser(__doc__)
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Only verify the final pattern from a previous successful run",
    )
    args = parser.parse_args()
    with qualification(args):
        capacity = args.capacity_mib << 20
        ios, card = validate_target(
            args.bus_width, capacity, args.clock_hz, args.actual_clock_hz
        )
        checks = []
        with direct_device(
            os.O_RDONLY if args.read_only else os.O_RDWR | os.O_SYNC
        ) as fd:
            for iteration in (1,) if args.read_only else (0, 1):
                for offset, size in write_cases(capacity):
                    data = expected_bytes(offset, size, iteration, capacity)
                    neighbors = [
                        (pos, direct_read(fd, pos, 512))
                        for pos in (offset - 512, offset + size)
                        if 0 <= pos <= capacity - 512
                    ]
                    if not args.read_only:
                        direct_write(fd, offset, data)
                        os.fsync(fd)
                    if direct_read(fd, offset, size) != data:
                        raise RuntimeError((offset, size, "readback mismatch"))
                    for pos, original in neighbors:
                        if direct_read(fd, pos, 512) != original:
                            raise RuntimeError((pos, "neighbor changed"))
                    checks.append(
                        dict(
                            iteration=iteration,
                            offset=offset,
                            bytes=size,
                            sha256=hashlib.sha256(data).hexdigest(),
                            passed=True,
                        )
                    )
        print(
            json.dumps(
                dict(
                    ios=ios,
                    cid=CID,
                    csd=(card / "csd").read_text().strip(),
                    read_only=args.read_only,
                    checks=checks,
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
