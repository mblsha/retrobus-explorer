#!/usr/bin/env python3
"""Bounded raw read/write check of the volatile SPADE DDR card on GKD.

Run only after DDR qualification and read-only checks have passed. This writes
small deterministic patterns to the FPGA test card and leaves them in place.
It refuses mounted media, a different card/controller, and an unexpected size.
"""

import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path

CAPACITY = 8 * 1024 * 1024
CID = "7f52425350414445101234567801916b"


def write_cases(capacity):
    assert capacity in (8 * 1024 * 1024, 256 * 1024 * 1024)
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
    assert 0 <= offset and 0 < size and offset + size <= capacity
    assert offset % 512 == size % 512 == 0
    assert iteration in (0, 1)
    return bytes(
        ((i * 53 + (i >> 8) * 7 + 29) & 255) ^ (255 * iteration)
        for i in range(offset, offset + size)
    )


def validate_target(
    bus_width, capacity=CAPACITY, clock_hz=1_000_000, actual_clock_hz=None
):
    actual_clock_hz = clock_hz if actual_clock_hz is None else actual_clock_hz
    assert 0 < actual_clock_hz <= clock_hz
    assert capacity in (8 * 1024 * 1024, 256 * 1024 * 1024)
    assert 0 < clock_hz <= 25_000_000
    host = Path("/sys/class/mmc_host/mmc1")
    assert "2a310000.mmc" in str(host.resolve())
    card = host / "mmc1:0001"
    disk = Path("/sys/class/block/mmcblk1")
    assert (card / "name").read_text().strip() == "SPADE"
    assert (card / "cid").read_text().strip() == CID
    assert (disk / "device").resolve() == card.resolve()
    assert (disk / "ro").read_text().strip() == "0"
    assert int((disk / "size").read_text()) * 512 == capacity
    assert not list((disk / "holders").iterdir())
    assert not any(
        line.split()[0].startswith("/dev/mmcblk1")
        for line in Path("/proc/mounts").read_text().splitlines()
    )
    assert not any(
        line.split()[0].startswith("/dev/mmcblk1")
        for line in Path("/proc/swaps").read_text().splitlines()[1:]
    )
    ios = Path("/sys/kernel/debug/mmc1/ios").read_text()
    assert f"({bus_width} bits)" in ios
    fields = dict(line.split(":", 1) for line in ios.splitlines())
    assert fields["clock"].strip() == f"{clock_hz} Hz"
    if "actual clock" in fields:
        assert fields["actual clock"].strip() == f"{actual_clock_hz} Hz"
    return ios, card


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Only verify the final pattern from a previous successful run",
    )
    parser.add_argument("--capacity-mib", type=int, choices=(8, 256), default=8)
    parser.add_argument("--clock-hz", type=int, default=1_000_000)
    parser.add_argument(
        "--actual-clock-hz",
        type=int,
        help="Expected divider output; defaults to requested clock",
    )
    args = parser.parse_args()
    capacity = args.capacity_mib << 20
    ios, card = validate_target(
        args.bus_width, capacity, args.clock_hz, args.actual_clock_hz
    )
    fd = os.open(
        "/dev/mmcblk1",
        os.O_DIRECT | (os.O_RDONLY if args.read_only else os.O_RDWR | os.O_SYNC),
    )

    def read(offset, size):
        with mmap.mmap(-1, size) as buf:
            os.lseek(fd, offset, os.SEEK_SET)
            assert os.readv(fd, [buf]) == size
            return buf[:]

    checks = []
    try:
        for iteration in (1,) if args.read_only else (0, 1):
            for offset, size in write_cases(capacity):
                data = expected_bytes(offset, size, iteration, capacity)
                neighbors = [
                    (pos, read(pos, 512))
                    for pos in (offset - 512, offset + size)
                    if 0 <= pos <= capacity - 512
                ]
                if not args.read_only:
                    with mmap.mmap(-1, size) as buf:
                        buf[:] = data
                        os.lseek(fd, offset, os.SEEK_SET)
                        assert os.writev(fd, [buf]) == size
                    os.fsync(fd)
                assert read(offset, size) == data, (offset, size, "readback mismatch")
                for pos, original in neighbors:
                    assert read(pos, 512) == original, (pos, "neighbor changed")
                checks.append(
                    dict(
                        iteration=iteration,
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
