#!/usr/bin/env python3
"""Read-only hardware check of the small deterministic SPADE test image.

Run on the GKD over SSH, after enumeration. This requires Linux O_DIRECT and
validates the exact external controller, card identity, read-only state, clock,
width, and lack of mounts before opening the block device.
"""

import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path


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
    actual_clock_hz = (
        args.clock_hz if args.actual_clock_hz is None else args.actual_clock_hz
    )
    assert 0 < actual_clock_hz <= args.clock_hz
    capacity = args.capacity_mib << 20
    assert 0 < args.clock_hz <= 25_000_000
    host = Path("/sys/class/mmc_host/mmc1")
    assert "2a310000.mmc" in str(host.resolve())
    card = host / "mmc1:0001"
    assert (card / "name").read_text().strip() == "SPADE"
    assert (card / "cid").read_text().strip() == "7f52425350414445101234567801916b"
    assert int(Path("/sys/class/block/mmcblk1/size").read_text()) * 512 == capacity
    assert Path("/sys/class/block/mmcblk1/device").resolve() == card.resolve()
    assert Path("/sys/class/block/mmcblk1/ro").read_text().strip() == (
        "0" if args.writable_card else "1"
    )
    assert not any(
        line.split()[0].startswith("/dev/mmcblk1")
        for line in Path("/proc/mounts").read_text().splitlines()
    )
    ios = Path("/sys/kernel/debug/mmc1/ios").read_text()
    assert f"({args.bus_width} bits)" in ios
    fields = dict(line.split(":", 1) for line in ios.splitlines())
    assert fields["clock"].strip() == f"{args.clock_hz} Hz"
    if "actual clock" in fields:
        assert fields["actual clock"].strip() == f"{actual_clock_hz} Hz"
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
            with mmap.mmap(-1, size) as buf:
                os.lseek(fd, offset, os.SEEK_SET)
                count = os.readv(fd, [buf])
                assert count == size, (count, size)
                data = buf[:]
            expected = bytes(
                (i * 37 + (i >> 8) * 11 + 17) & 255 if i < 65536 else 0
                for i in range(offset, offset + size)
            )
            assert data == expected, (offset, size, "data mismatch")
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
