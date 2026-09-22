#!/usr/bin/env python3
"""Run every microSD Spade/Cocotb and host check; no hardware access."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

GATEWARE = Path(__file__).resolve().parents[1]
CASES = [
    ("microsd-pin-tester", "probe_core", "test_probe"),
    ("microsd-pin-tester", "probe_uart", "test_uart"),
    ("microsd-emulator", "sd_frontend", "test_sd"),
    ("microsd-emulator", "sd_frontend", "test_sd_write"),
    ("microsd-emulator", "sd_frontend", "test_sd_write_busy"),
    ("microsd-emulator", "bram_backend", "test_storage"),
    ("microsd-emulator", "ddr_backend", "test_ddr"),
    ("microsd-emulator", "ddr_byte_writer", "test_byte_writer"),
    ("microsd-emulator", "native_bist", "test_native_bist"),
    ("microsd-emulator", "sd_clock_meter", "test_clock_meter"),
    ("microsd-emulator", "qualified_ddr", "test_qualified_ddr"),
    ("microsd-emulator", "image_loader", "test_loader"),
    ("microsd-emulator", "bram_emulator", "test_integration"),
    ("microsd-emulator", "ddr_emulator", "test_ddr_integration"),
    ("microsd-emulator", "ddr_emulator", "test_ddr_rw"),
    ("microsd-emulator", "ddr_emulator", "test_ddr_ownership"),
    ("microsd-emulator", "emulator_uart", "test_emulator_uart"),
    ("microsd-emulator", "native_cdc", "test_native_cdc"),
    ("microsd-emulator", "native_stage", "test_native_stage"),
    ("microsd-emulator", "ddr_uart", "test_ddr_uart"),
    ("microsd-emulator", "ddr_uart_80", "test_ddr_uart"),
    ("microsd-emulator", "ddr_uart_100", "test_ddr_uart"),
    ("microsd-emulator", "ddr_emulator_cdc", "test_ddr_rw"),
    ("microsd-emulator", "sd_write_receiver", "test_write_rx"),
    ("microsd-emulator", "sd_write_response", "test_write_response"),
    ("microsd-emulator", "ddr_sector_writer", "test_sector_writer"),
    ("microsd-emulator", "sd_write_transaction", "test_write_transaction"),
]
# `--fast-sd` replaces the profile rather than adding one, so CI exercised the
# native write path only at 25 MHz with the prepared output registers, and a
# default-profile regression in that path survived twenty commits unnoticed.
# These two cases run in both profiles. That costs about nine more minutes and
# covers the 1 MHz card clock, the slow command and data launch edges, and the
# H700/MMC cases the fast profile cannot build. The `test_ddr_rw` suites stay
# fast-only: ten to fifteen minutes each for the write path `test_sd_write`
# already covers here in three.
BOTH_PROFILES = {
    ("sd_frontend", "test_sd"),
    ("sd_frontend", "test_sd_write"),
}


def fast_profile(top):
    """The 100 MHz / 25 MHz SD path and 100-to-80 MHz CDC overrides."""
    env = dict(
        MICROSD_SYS_PERIOD_NS="12.5",
        MICROSD_FAST_MODE="0",
        MICROSD_HALF_NS="41",
    )
    if top in ("sd_frontend", "ddr_emulator", "ddr_emulator_cdc"):
        env.update(
            MICROSD_SYS_PERIOD_NS="10",
            MICROSD_FAST_MODE="1",
            MICROSD_HALF_NS="19.9",
            MICROSD_CLOCK_JITTER="0",
            MICROSD_SAMPLE_ADVANCE_NS="8",
        )
    if top == "native_cdc":
        env.update(MICROSD_CDC_SRC_NS="10", MICROSD_CDC_DST_NS="12.5")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extra-only",
        action="store_true",
        help="CI: skip the two default project tops already tested by the registry",
    )
    parser.add_argument(
        "--fast-sd",
        action="store_true",
        help="Test the 100 MHz / 25 MHz SD path and 100-to-80 MHz CDC",
    )
    args = parser.parse_args()
    out = GATEWARE / "build/microsd-tests"
    out.mkdir(parents=True, exist_ok=True)
    for command in (
        [sys.executable, "tools/project_inventory.py", "--check"],
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tools",
            "-p",
            "test_microsd*.py",
        ],
    ):
        subprocess.run(command, cwd=GATEWARE, check=True)
    for project, top, module in CASES:
        if args.extra_only:
            if module == "test_probe":
                continue
            if module == "test_sd" and not args.fast_sd:
                continue
        profiles = [("", fast_profile(top) if args.fast_sd else {})]
        if args.fast_sd and (top, module) in BOTH_PROFILES:
            profiles.append(("-default", None))
        for suffix, overrides in profiles:
            if overrides is None:
                # The default profile is the absence of every knob, so drop
                # any the caller exported rather than layering over them.
                env = {
                    k: v
                    for k, v in os.environ.items()
                    if not k.startswith("MICROSD_")
                }
            else:
                env = dict(os.environ)
                env.update(overrides)
            print(f"Testing {project}: {top} ({module}{suffix})", flush=True)
            name = f"{top}-{module}{suffix}"
            (out / f"{name}-parameters.json").write_text(
                json.dumps(
                    {k: v for k, v in env.items() if k.startswith("MICROSD_")}, indent=2
                )
                + "\n"
            )
            with (out / f"{name}.log").open("w") as log:
                subprocess.run(
                    [
                        sys.executable,
                        "tools/run_tb.py",
                        "--project",
                        f"projects/{project}",
                        "--top",
                        top,
                        "--test-module",
                        module,
                    ],
                    cwd=GATEWARE,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            (out / f"{name}.xml").write_bytes(
                (GATEWARE / f"projects/{project}/test/results.xml").read_bytes()
            )
    print("All microSD tests passed.", flush=True)


if __name__ == "__main__":
    main()
