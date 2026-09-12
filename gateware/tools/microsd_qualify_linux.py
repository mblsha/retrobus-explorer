#!/usr/bin/env python3
"""Run a hardware check while rejecting controller errors and hidden recovery.

Run as root on the GKD. The command is an existing guarded SPADE test helper.
This wrapper never clears kernel logs or controller counters.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

CID = "7f52425350414445101234567801916b"
DEBUG = Path("/sys/kernel/debug/mmc1")
CARD = Path("/sys/class/mmc_host/mmc1/mmc1:0001")


def snapshot():
    assert "2a310000.mmc" in str(CARD.resolve())
    assert (CARD / "cid").read_text().strip() == CID
    assert not any(
        line.split()[0].startswith("/dev/mmcblk1")
        for line in Path("/proc/mounts").read_text().splitlines()
    )
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual-clock-hz", type=int, required=True)
    parser.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    parser.add_argument(
        "--filesystem-test",
        action="store_true",
        help="Allow only partition listings and the known FAT charset notice; retain them in evidence",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    assert command, "A guarded test command is required"
    before = snapshot()
    problems, _ = validate(before, before, args.actual_clock_hz, args.bus_width)
    assert not problems, problems
    result = subprocess.run(command, capture_output=True, text=True)
    try:
        after = snapshot()
        problems, relevant = validate(
            before, after, args.actual_clock_hz, args.bus_width, args.filesystem_test
        )
    except (OSError, AssertionError, ValueError) as error:
        after = {}
        relevant = []
        problems = [f"post-test evidence unavailable: {type(error).__name__}: {error}"]
    if result.returncode:
        problems.append(f"test command exited {result.returncode}")
    print(
        json.dumps(
            {
                "passed": not problems,
                "problems": problems,
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "before": {k: v for k, v in before.items() if k != "dmesg"},
                "after": {k: v for k, v in after.items() if k != "dmesg"},
                "kernel_messages": relevant,
            },
            indent=2,
        )
    )
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
