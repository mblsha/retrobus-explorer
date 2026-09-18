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


def transitions(samples: list[tuple[float, dict]], progress: int = 8192) -> list[dict]:
    """Collapse a poll series to the moments card activity changed.

    Read counters advance continuously while a transfer streams, so they do not
    mark a transition by themselves; a new command, a write, or a completed
    multiblock read does. Each entry carries the sectors served since the
    previous one, which is what a stage costs.

    A single transfer can also run for tens of seconds without any of that
    changing, which is exactly the failure worth studying, so a row is also
    emitted every `progress` sectors to keep a long stream legible. The last
    sample is always kept, so a stream that never ends still reports where it
    reached.
    """
    entries: list[dict] = []
    previous_key = None
    previous_reads = None
    for index, (elapsed, trace) in enumerate(samples):
        summary = summarize(trace)
        key = (
            summary["frames"],
            summary["last_command"],
            summary["argument"],
            summary["writes"],
            tuple(summary["multiblock"]),
        )
        streamed = (
            progress
            and previous_reads is not None
            and summary["reads"] - previous_reads >= progress
        )
        last = index + 1 == len(samples)
        if key == previous_key and not streamed and not last:
            continue
        entry = dict(summary)
        entry["elapsed"] = round(elapsed, 3)
        entry["sectors_since"] = (
            None if previous_reads is None else summary["reads"] - previous_reads
        )
        entry["streaming"] = bool(streamed)
        entries.append(entry)
        previous_key = key
        previous_reads = summary["reads"]
    return entries


def power(cli: Path, channel: str, state: str, wait: bool = True):
    """Switch the target's channel, optionally without waiting for the CLI.

    Waiting for the power-on to return is what made this measurement wrong.
    The CLI has to start a Node process and open a serial port before it can
    switch anything, and how long that takes varies by seconds, so a clock
    started when it returns has already lost an unknown amount of the boot. A
    run that lost two seconds looked two seconds faster. Power-on is therefore
    launched and left running while polling begins immediately, and the clock
    is re-zeroed on the first card clock edge the FPGA actually sees.

    Power-off stays synchronous: an armed card facing a target whose state is
    unknown is the one condition this bench must never leave behind.
    """
    command = ["npm", "run", "start", "--silent", "--", channel, state]
    if not wait:
        return subprocess.Popen(
            command, cwd=cli, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    subprocess.run(
        command, cwd=cli, capture_output=True, timeout=120, check=False,
    )
    return None


def first_command_index(samples: list[tuple[float, dict]], baseline: dict) -> int | None:
    """Return the first sample in which the host issued a command.

    The obvious anchor, the first clock edge, does not work: with the target
    unpowered the card's clock pin floats and the edge counter still advances,
    measured here at about fifty edges a second, so every sample after the
    baseline shows more edges than it and the zero lands immediately. The
    command counters do not move at all while the target is off, because a
    floating line does not produce a frame that passes CRC7. The host's first
    command follows its first clock edge by microseconds, which is far below
    the resolution of this poll, so it is the same instant for this purpose.
    """
    return next(
        (
            index
            for index, (_, trace) in enumerate(samples)
            if index and trace["command_frames"] > baseline["command_frames"]
        ),
        None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="images.py session file")
    parser.add_argument("--observe", type=float, default=45.0)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument(
        "--settle", type=float, default=6.0,
        help="Seconds to hold the target powered off before starting. Trials "
        "run back to back have repeatedly produced a cold start with no card "
        "activity at all, which a longer off interval avoids.",
    )
    parser.add_argument(
        "--progress", type=int, default=8192,
        help="Also emit a row every N sectors so a long transfer stays legible",
    )
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
        power(arguments.psu_cli, arguments.channel, "off")
        time.sleep(arguments.settle)
        launch = power(arguments.psu_cli, arguments.channel, "on", wait=False)
        start = time.monotonic()
        while time.monotonic() - start < arguments.observe:
            samples.append((time.monotonic() - start, client.trace()))
            time.sleep(arguments.interval)
        launch.wait(timeout=120)
    finally:
        power(arguments.psu_cli, arguments.channel, "off")
        time.sleep(2)
        client.command(images.Opcode.DISARM)

    # Everything is reported from the host's first command rather than from the
    # power-on, so the figures do not carry the power CLI's start-up time.
    edge = first_command_index(samples, baseline)
    if edge is None:
        raise SystemExit("the card saw no command; the target did not start")
    zero = samples[edge][0]
    # The first command is only known to be the first if a poll saw the card
    # quiet before it. Reads start within a poll of it either way, so their
    # counter says nothing about whether polling began in time.
    sound = edge > 1
    samples = [(elapsed - zero, trace) for elapsed, trace in samples]
    timeline = transitions(samples, arguments.progress)
    for entry in timeline:
        where = ""
        if arguments.image is not None and entry["reads"] != baseline["read_requests"]:
            where = " " + boot_debug.describe_lba(arguments.image, entry["read_lba"])
        print(
            f"t={entry['elapsed']:7.2f}s CMD{entry['last_command']:<2d} "
            f"arg={entry['argument']:<11d} frames={entry['frames']:>4d} "
            f"writes={entry['writes']:>2d} lba={entry['read_lba']:>7d} "
            f"{'stream' if entry['streaming'] else '      '}{where}"
        )
    # Every capture register resets when the card is disarmed, so the block
    # capture and its fabric timestamps have to be reported from the last
    # in-run sample rather than queried afterwards.
    enhanced = samples[-1][1].get("enhanced", {})
    block = enhanced.get("first_mmc_block", {})
    if block.get("state") not in (None, "idle"):
        timing = enhanced.get("timing", {})
        print(
            f"\ncaptured sector {block['capture_lba']}: {block['state']}, "
            f"{block['payload_bits']} payload bits, "
            f"crc {'match' if block['crc_match'] else 'MISMATCH'}, "
            f"end bit {'set' if block['end_bit'] else 'missing'}"
        )
        if block.get("first_32_bytes"):
            print(f"  first bytes {block['first_32_bytes']}")
        span = timing.get("first_block_end", 0) - timing.get("data_start", 0)
        print(
            f"  fabric ticks: r1_end {timing.get('r1_end')}, "
            f"data_start {timing.get('data_start')}, "
            f"block_end {timing.get('first_block_end')} (span {span}), "
            f"edges {timing.get('data_start_edge')}..{timing.get('first_block_end_edge')}"
        )

    print(
        f"\nfirst host command {zero:.2f}s after the power command was issued; "
        + (
            "the clock starts there"
            if sound
            else "NO POLL SAW THE CARD QUIET FIRST, so this run's zero is "
            "unknown and its total must be discarded"
        )
    )
    final = summarize(samples[-1][1])
    print(
        f"\nlast read LBA {final['read_lba']}, "
        f"served {final['reads'] - baseline['read_requests']} sectors, "
        f"{final['writes'] - baseline['writes']} writes, "
        f"{final['valid'] - baseline['valid_commands']} valid command frames, "
        f"{final['invalid'] - baseline['invalid_frames']} invalid"
    )
    if arguments.output is not None:
        arguments.output.write_text(
            json.dumps(
                {"zero_is_sound": sound, "power_to_first_edge": round(zero, 3),
                 "timeline": timeline},
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
