#!/usr/bin/env python3
"""Run a standardized RG35XX Plus cold start and report what the card saw.

The target has no serial output, so a boot is observed entirely through the
card: this powers the target's own PSU channel, polls the passive SD trace, and
collapses the poll series to the points where card activity changed. Counters
are cumulative from FPGA configuration, so a baseline is taken before power-on
and every figure is reported as a delta.

The target is always powered off and the card frontend disarmed afterwards,
including on failure, so an armed FPGA is never left facing a dead target.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import images  # noqa: E402
import rg35xx_boot_debug as boot_debug  # noqa: E402


def summarize(trace: dict) -> dict:
    """Reduce one trace reply to the fields that describe card activity."""
    status = trace["protocol_status"]
    return {
        "frames": trace["command_frames"],
        "valid": trace["valid_commands"],
        "invalid": trace["invalid_frames"],
        "last_command": trace["last_command"],
        "argument": trace["last_argument"],
        "reads": trace["read_requests"],
        "read_lba": trace["last_read_lba"],
        "writes": trace["writes"],
        "card_state": status["card_state"],
        "wide_bus": status["wide_bus"],
        "idle_data_high": status.get("idle_data_high"),
        "clock_edges": trace["clock_edges"],
        "multiblock": [
            (entry["lba"], entry["blocks"]) for entry in trace["recent_multiblock_reads"]
        ],
    }


def transitions(samples: list[tuple[float, dict]]) -> list[dict]:
    """Collapse a poll series to the moments card activity changed.

    Read counters advance continuously while a transfer streams, so they do not
    mark a transition by themselves; a new command, a write, or a completed
    multiblock read does. Each entry carries the sectors served since the
    previous one, which is what a stage costs.
    """
    entries: list[dict] = []
    previous_key = None
    previous_reads = None
    for elapsed, trace in samples:
        summary = summarize(trace)
        key = (
            summary["frames"],
            summary["last_command"],
            summary["argument"],
            summary["writes"],
            tuple(summary["multiblock"]),
        )
        if key == previous_key:
            continue
        entry = dict(summary)
        entry["elapsed"] = round(elapsed, 3)
        entry["sectors_since"] = (
            None if previous_reads is None else summary["reads"] - previous_reads
        )
        entries.append(entry)
        previous_key = key
        previous_reads = summary["reads"]
    return entries


def power(cli: Path, channel: str, state: str) -> None:
    subprocess.run(
        ["npm", "run", "start", "--silent", "--", channel, state],
        cwd=cli, capture_output=True, timeout=120, check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="images.py session file")
    parser.add_argument("--observe", type=float, default=45.0)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument(
        "--psu-cli", type=Path, default=os.environ.get("MDP_CLI"),
        help="Miniware MDP CLI checkout (default: $MDP_CLI)",
    )
    parser.add_argument(
        "--channel", default="psu2",
        help="PSU channel powering the target. psu2 is the RG35XX; psu1 is the "
        "Zaurus on this bench and must not be switched by a card trial.",
    )
    parser.add_argument(
        "--image", type=Path,
        help="Boot image used to name the LBAs each stage touched",
    )
    parser.add_argument("--output", type=Path, help="Write the timeline as JSON")
    arguments = parser.parse_args()
    if arguments.psu_cli is None:
        parser.error("--psu-cli or $MDP_CLI is required to power the target")

    client = images.Images(state=arguments.state)
    baseline = client.trace()
    if not baseline["armed"]:
        raise SystemExit("card is not armed; upload and verify an image first")

    samples: list[tuple[float, dict]] = [(0.0, baseline)]
    try:
        power(arguments.psu_cli, arguments.channel, "on")
        start = time.monotonic()
        while time.monotonic() - start < arguments.observe:
            samples.append((time.monotonic() - start, client.trace()))
            time.sleep(arguments.interval)
    finally:
        power(arguments.psu_cli, arguments.channel, "off")
        time.sleep(2)
        client.command(images.Opcode.DISARM)

    timeline = transitions(samples)
    for entry in timeline:
        where = ""
        if arguments.image is not None and entry["reads"] != baseline["read_requests"]:
            where = " " + boot_debug.describe_lba(arguments.image, entry["read_lba"])
        print(
            f"t={entry['elapsed']:7.2f}s CMD{entry['last_command']:<2d} "
            f"arg={entry['argument']:<11d} frames={entry['frames']:>4d} "
            f"writes={entry['writes']:>2d} lba={entry['read_lba']:>7d}"
            f"{where}"
        )
    final = summarize(samples[-1][1])
    print(
        f"\nserved {final['reads'] - baseline['read_requests']} sectors, "
        f"{final['writes'] - baseline['writes']} writes, "
        f"{final['valid'] - baseline['valid_commands']} valid command frames, "
        f"{final['invalid'] - baseline['invalid_frames']} invalid"
    )
    if arguments.output is not None:
        arguments.output.write_text(json.dumps(timeline, indent=2) + "\n")


if __name__ == "__main__":
    main()
