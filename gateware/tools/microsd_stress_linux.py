#!/usr/bin/env python3
"""Destructive integrity/throughput test of positively identified volatile FPGA SD.

Writes an explicit prefix, then random 4 KiB replacements. Verify every block
in the prefix and optionally hash all untouched space before/after to catch
aliases and collateral corruption. The shared host module enforces target identity and exact I/O lengths.
"""

import argparse
from microsd_qualify_linux import qualification
import hashlib
import json
import mmap
import os
import random
import sys
import time

from microsd_host import validate_target, read_into, write_from, direct_read

BLOCK = 4096


def payload(block, generation, seed):
    if not (0 <= block < 65536 and 0 <= generation < 1 << 32):
        raise RuntimeError(
            "Check failed: 0 <= block < 65536 and 0 <= generation < 1 << 32"
        )
    if not (0 <= seed < 1 << 64):
        raise RuntimeError("Check failed: 0 <= seed < 1 << 64")
    key = (
        seed.to_bytes(8, "little")
        + block.to_bytes(4, "little")
        + generation.to_bytes(4, "little")
    )
    return hashlib.shake_256(key).digest(BLOCK)


def verify_windows(args, capacity):
    versions = [0] * (capacity // BLOCK)
    rng = random.Random(args.seed)
    for _ in range(args.passes * args.random_writes):
        versions[rng.randrange(len(versions))] += 1
    checks = []
    fd = os.open("/dev/mmcblk1", os.O_RDONLY | os.O_DIRECT)
    try:
        for offset in (0, 127 << 20, 255 << 20):
            size = 1 << 20
            expected = b"".join(
                payload(i, versions[i], args.seed)
                for i in range(offset // BLOCK, (offset + size) // BLOCK)
            )
            actual = direct_read(fd, offset, size)
            if actual != expected:
                raise RuntimeError(("data mismatch", offset))
            checks.append(
                dict(
                    offset=offset, bytes=size, sha256=hashlib.sha256(actual).hexdigest()
                )
            )
    finally:
        os.close(fd)
    print(
        json.dumps(dict(passed=True, configuration=vars(args), checks=checks), indent=2)
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capacity-mib", type=int, choices=(8, 256), required=True)
    p.add_argument("--clock-hz", type=int, required=True)
    p.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    p.add_argument("--span-mib", type=int, required=True)
    p.add_argument("--random-writes", type=int, default=256)
    p.add_argument("--passes", type=int, default=2)
    p.add_argument("--seed", type=int, default=20260908)
    p.add_argument("--verify-whole-card", action="store_true")
    p.add_argument(
        "--read-only",
        action="store_true",
        help="Check 1 MiB windows after a completed full-card stress run, e.g. after changing bus width",
    )
    p.add_argument(
        "--actual-clock-hz",
        type=int,
        help="Expected divider output; defaults to requested clock",
    )
    args = p.parse_args()
    with qualification(args):
        capacity = args.capacity_mib << 20
        span = args.span_mib << 20
        if not (0 < span <= capacity and args.random_writes >= 0 and (args.passes > 0)):
            raise RuntimeError(
                "Check failed: 0 < span <= capacity and args.random_writes >= 0 and (args.passes > 0)"
            )
        ios, _ = validate_target(
            args.bus_width, capacity, args.clock_hz, args.actual_clock_hz
        )
        if args.read_only:
            if span != capacity or capacity != 256 << 20:
                raise RuntimeError(
                    "Cross-width readback requires the completed full 256 MiB stress run"
                )
            return verify_windows(args, capacity)
        rng = random.Random(args.seed)
        versions = [0] * (span // BLOCK)
        fd = os.open("/dev/mmcblk1", os.O_RDWR | os.O_DIRECT | os.O_SYNC)
        buf = mmap.mmap(-1, 65536)
        results = []

        def read(offset, size):
            view = memoryview(buf)[:size]
            try:
                read_into(fd, view, offset)
                return bytes(view)
            finally:
                view.release()

        def write(offset, data):
            if not (offset % BLOCK == 0 and offset + len(data) <= span):
                raise RuntimeError(
                    "Check failed: offset % BLOCK == 0 and offset + len(data) <= span"
                )
            buf[: len(data)] = data
            view = memoryview(buf)[: len(data)]
            try:
                write_from(fd, view, offset)
            finally:
                view.release()

        def outside_hash():
            digest = hashlib.sha256()
            for pos in range(span, capacity, 65536):
                digest.update(read(pos, min(65536, capacity - pos)))
            return digest.hexdigest()

        def verify_all(label):
            start = time.monotonic()
            for pos in range(0, span, 65536):
                size = min(65536, span - pos)
                actual = read(pos, size)
                expected = b"".join(
                    payload(i, versions[i], args.seed)
                    for i in range(pos // BLOCK, (pos + size) // BLOCK)
                )
                if actual != expected:
                    raise RuntimeError(("full readback mismatch", pos, label))
            elapsed = time.monotonic() - start
            print(
                f"{label}: {span} bytes verified in {elapsed:.2f}s",
                file=sys.stderr,
                flush=True,
            )
            results.append(
                dict(
                    stage=label,
                    bytes=span,
                    seconds=elapsed,
                    bytes_per_second=span / elapsed,
                    passed=True,
                )
            )

        try:
            untouched = outside_hash() if args.verify_whole_card else None
            start = time.monotonic()
            for pos in range(0, span, 65536):
                write(
                    pos,
                    b"".join(
                        payload(i, 0, args.seed)
                        for i in range(
                            pos // BLOCK, min((pos + 65536) // BLOCK, len(versions))
                        )
                    ),
                )
            os.fsync(fd)
            elapsed = time.monotonic() - start
            results.append(
                dict(
                    stage="sequential-write",
                    bytes=span,
                    seconds=elapsed,
                    bytes_per_second=span / elapsed,
                    passed=True,
                )
            )
            print(
                f"sequential-write: {span} bytes in {elapsed:.2f}s",
                file=sys.stderr,
                flush=True,
            )
            verify_all("initial-full-readback")
            for iteration in range(args.passes):
                start = time.monotonic()
                for _ in range(args.random_writes):
                    index = rng.randrange(len(versions))
                    versions[index] += 1
                    data = payload(index, versions[index], args.seed)
                    # Check immediate neighbors on both sides before and after.
                    neighbors = {
                        n: read(n * BLOCK, BLOCK)
                        for n in (index - 1, index + 1)
                        if 0 <= n < capacity // BLOCK
                    }
                    write(index * BLOCK, data)
                    if read(index * BLOCK, BLOCK) != data:
                        raise RuntimeError(("random mismatch", index))
                    for n, old in neighbors.items():
                        if read(n * BLOCK, BLOCK) != old:
                            raise RuntimeError(("neighbor corruption", n))
                os.fsync(fd)
                results.append(
                    dict(
                        stage=f"mixed-round-{iteration}",
                        operations=args.random_writes,
                        seconds=time.monotonic() - start,
                        passed=True,
                    )
                )
                verify_all(f"full-readback-{iteration}")
                if untouched is not None:
                    if outside_hash() != untouched:
                        raise RuntimeError("untouched DDR region changed")
            print(
                json.dumps(
                    dict(
                        configuration=vars(args),
                        ios=ios,
                        direct_io=True,
                        results=results,
                        untouched_sha256=untouched,
                        passed=True,
                    ),
                    indent=2,
                )
            )
        finally:
            buf.close()
            os.close(fd)


if __name__ == "__main__":
    main()
