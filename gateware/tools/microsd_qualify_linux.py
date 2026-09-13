#!/usr/bin/env python3
"""Run a hardware check while rejecting controller errors and hidden recovery.

Used automatically by the guarded transfer checks. Never clears kernel logs
or controller counters.
"""

from contextlib import contextmanager
import sys
import json
import re
import subprocess
from pathlib import Path

from microsd_host import CID, require_unused

DEBUG = Path("/sys/kernel/debug/mmc1")
CARD = Path("/sys/class/mmc_host/mmc1/mmc1:0001")


def snapshot():
    if "2a310000.mmc" not in str(CARD.resolve()):
        raise RuntimeError("Wrong external MMC controller during qualification")
    if (CARD / "cid").read_text().strip() != CID:
        raise RuntimeError("Wrong card CID during qualification")
    require_unused(Path("/sys/class/block/mmcblk1"))
    return {
        "uptime_seconds": float(Path("/proc/uptime").read_text().split()[0]),
        "power_control": (CARD / "power/control").read_text().strip(),
        "runtime_status": (CARD / "power/runtime_status").read_text().strip(),
        "max_sectors_kb": Path("/sys/class/block/mmcblk1/queue/max_sectors_kb")
        .read_text()
        .strip(),
        "ios": (DEBUG / "ios").read_text(),
        "errors": (DEBUG / "err_stats").read_text(),
        "dmesg": subprocess.check_output(["dmesg"], text=True).splitlines(),
    }


def validate(before, after, clock, width, filesystem_test=False):
    problems = []
    for label, state in [("before", before), ("after", after)]:
        fields = dict(line.split(":", 1) for line in state["ios"].splitlines())
        actual = fields.get("actual clock", fields["clock"]).strip()
        if actual != f"{clock} Hz" or f"({width} bits)" not in fields["bus width"]:
            problems.append(f"{label}: unexpected actual clock or bus width")
        counters = re.findall(r":\s*(\d+)\s*$", state["errors"], re.M)
        if not counters or any(int(n) for n in counters):
            problems.append(f"{label}: missing or nonzero error counters")
    for field in ("power_control", "max_sectors_kb"):
        if field in before and before[field] != after.get(field):
            problems.append(f"{field} changed during the test")
    old, new = before["dmesg"], after["dmesg"]
    if not old or old[-1] not in new:
        problems.append("kernel log continuity cannot be proven")
        delta = new
    else:
        delta = new[new.index(old[-1]) + 1 :]
    relevant = [line for line in delta if re.search(r"mmc1|mmcblk1|2a310000", line)]
    unexpected = relevant
    if filesystem_test:

        def expected_filesystem_message(line):
            message = re.sub(r"^\[\s*\d+\.\d+\]\s*", "", line)
            return bool(re.fullmatch(r"mmcblk1:(?: p\d+)*", message)) or message == (
                "FAT-fs (mmcblk1): utf8 is not a recommended IO charset for FAT "
                "filesystems, filesystem will be case sensitive!"
            )

        unexpected = [
            line for line in relevant if not expected_filesystem_message(line)
        ]
    if unexpected:
        problems.append("external MMC kernel messages appeared during the test")
    return problems, relevant


@contextmanager
def qualification(args, *, filesystem_test=False):
    """Fail a normal qualification command on errors, recovery, or lost evidence.

    Transfer results remain on stdout; monitoring evidence is JSON on stderr.
    A transfer exception is preserved, and post-test evidence is still collected.
    """
    clock = args.actual_clock_hz if args.actual_clock_hz is not None else args.clock_hz
    before = snapshot()
    problems, _ = validate(before, before, clock, args.bus_width)
    if problems:
        raise RuntimeError(problems)
    transfer_failed = False
    try:
        yield
    except BaseException:
        transfer_failed = True
        raise
    finally:
        try:
            after = snapshot()
            problems, relevant = validate(
                before, after, clock, args.bus_width, filesystem_test
            )
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            after, relevant = {}, []
            problems = [
                f"Post-test evidence unavailable: {type(error).__name__}: {error}"
            ]
        if transfer_failed:
            problems.append("Transfer test failed")
        print(
            json.dumps(
                dict(
                    qualification_passed=not problems,
                    problems=problems,
                    before={k: v for k, v in before.items() if k != "dmesg"},
                    after={k: v for k, v in after.items() if k != "dmesg"},
                    kernel_messages=relevant,
                ),
                indent=2,
            ),
            file=sys.stderr,
        )
        if problems and not transfer_failed:
            raise RuntimeError(problems)
