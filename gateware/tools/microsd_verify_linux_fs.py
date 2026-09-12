#!/usr/bin/env python3
"""Small FAT12/FAT16 test on the verified volatile SPADE card, after raw tests pass.

Requires microsd_verify_linux_rw.py alongside this file. This formats only the
positively identified external FPGA card and leaves it unmounted afterwards.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from microsd_verify_linux_rw import CID, validate_target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    parser.add_argument("--capacity-mib", type=int, choices=(8, 256), default=8)
    parser.add_argument("--clock-hz", type=int, default=1_000_000)
    parser.add_argument(
        "--actual-clock-hz",
        type=int,
        help="Expected divider output; defaults to requested clock",
    )
    args = parser.parse_args()
    ios, card = validate_target(
        args.bus_width, args.capacity_mib << 20, args.clock_hz, args.actual_clock_hz
    )
    mountpoint = Path(tempfile.mkdtemp(prefix="codex-spade-fs-"))
    mounted = False
    commands = []

    def run(*args):
        result = subprocess.run(args, check=True, capture_output=True, text=True)
        commands.append(dict(argv=args, stdout=result.stdout, stderr=result.stderr))

    payloads = {
        "CHECK.TXT": b"SPADE Arty A7 DDR-backed native SD filesystem test\n",
        "TESTDIR/RENAMED.BIN": bytes(
            (i * 29 + (i >> 8) * 13 + 5) & 255 for i in range(65536)
        ),
        "TESTDIR/SMALL.BIN": bytes((i * 11 + 17) & 255 for i in range(4096)),
    }
    try:
        run(
            "mkfs.fat",
            "-F",
            "16" if args.capacity_mib == 256 else "12",
            "-n",
            "SPADETEST",
            "/dev/mmcblk1",
        )
        run("fsck.fat", "-n", "/dev/mmcblk1")
        run(
            "mount",
            "-t",
            "vfat",
            "-o",
            "rw,sync,nodev,nosuid,noexec",
            "/dev/mmcblk1",
            str(mountpoint),
        )
        mounted = True
        (mountpoint / "TESTDIR").mkdir()
        for name, data in payloads.items():
            path = mountpoint / (
                "TESTDIR/ORIGINAL.BIN" if name.endswith("RENAMED.BIN") else name
            )
            with path.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        (mountpoint / "TESTDIR/ORIGINAL.BIN").rename(mountpoint / "TESTDIR/RENAMED.BIN")
        removed = mountpoint / "DELETE.TXT"
        removed.write_bytes(b"temporary test entry\n")
        removed.unlink()
        run("umount", str(mountpoint))
        mounted = False
        run("fsck.fat", "-n", "/dev/mmcblk1")
        # Recheck identity before remounting. All buffered writes were flushed
        # by the unmount; verification comes through a fresh read-only mount.
        validate_target(
            args.bus_width, args.capacity_mib << 20, args.clock_hz, args.actual_clock_hz
        )
        run(
            "mount",
            "-t",
            "vfat",
            "-o",
            "ro,nodev,nosuid,noexec",
            "/dev/mmcblk1",
            str(mountpoint),
        )
        mounted = True
        checks = []
        for name, data in payloads.items():
            actual = (mountpoint / name).read_bytes()
            assert actual == data, (name, "filesystem readback mismatch")
            checks.append(
                dict(
                    path=name,
                    bytes=len(actual),
                    sha256=hashlib.sha256(actual).hexdigest(),
                    passed=True,
                )
            )
        assert not (mountpoint / "DELETE.TXT").exists()
        assert not (mountpoint / "TESTDIR/ORIGINAL.BIN").exists()
        run("umount", str(mountpoint))
        mounted = False
        run("fsck.fat", "-n", "/dev/mmcblk1")
        print(
            json.dumps(
                dict(
                    ios=ios,
                    cid=CID,
                    csd=(card / "csd").read_text().strip(),
                    checks=checks,
                    commands=commands,
                    unmounted=True,
                ),
                indent=2,
            )
        )
    finally:
        if mounted:
            subprocess.run(["umount", str(mountpoint)], check=True)
        mountpoint.rmdir()


if __name__ == "__main__":
    main()
