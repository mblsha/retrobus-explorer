#!/usr/bin/env python3
"""Read-only cross-width/large-request check after full microsd_stress_linux.

The seed, passes and random-write count must match the completed 256 MiB run.
Does not replace that run's complete memory readbacks.
"""

import argparse
import hashlib
import json
import mmap
import os
import random
from microsd_stress_linux import BLOCK, payload
from microsd_verify_linux_rw import validate_target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    p.add_argument("--clock-hz", type=int, required=True)
    p.add_argument("--actual-clock-hz", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--passes", type=int, default=2)
    p.add_argument("--random-writes", type=int, default=1024)
    a = p.parse_args()
    assert 0 < a.passes <= 10 and 0 <= a.random_writes <= 65536
    capacity = 256 << 20
    validate_target(a.bus_width, capacity, a.clock_hz, a.actual_clock_hz)
    versions = [0] * (capacity // BLOCK)
    rng = random.Random(a.seed)
    for _ in range(a.passes * a.random_writes):
        versions[rng.randrange(len(versions))] += 1
    checks = []
    fd = os.open("/dev/mmcblk1", os.O_RDONLY | os.O_DIRECT)
    try:
        with mmap.mmap(-1, 1 << 20) as buf:
            for offset in (0, 127 << 20, 255 << 20):
                expected = b"".join(
                    payload(i, versions[i], a.seed)
                    for i in range(offset // BLOCK, (offset + len(buf)) // BLOCK)
                )
                assert os.preadv(fd, [buf], offset) == len(buf)
                assert buf[:] == expected, ("data mismatch", offset)
                checks.append(
                    dict(
                        offset=offset,
                        bytes=len(buf),
                        sha256=hashlib.sha256(buf).hexdigest(),
                    )
                )
    finally:
        os.close(fd)
    print(json.dumps(dict(passed=True, configuration=vars(a), checks=checks), indent=2))


if __name__ == "__main__":
    main()
